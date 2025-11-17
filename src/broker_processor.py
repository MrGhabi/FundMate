"""
Core broker statement processor module.
Contains the main business logic for processing broker statements and orchestrating the workflow.
"""

from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from loguru import logger
import re

from src.pdf_processor import PDFProcessor
from src.excel_parser import ExcelPositionParser
from src.price_fetcher import PriceFetcher, get_stock_price
from src.utils import setup_logging, validate_date_format, print_asset_summary, get_option_multiplier
from src.config import settings
from src.exchange_rate_handler import exchange_handler
from src.enums import PositionContext
from src.position import Position
from src.llm_handler import LLMHandler


def extract_occ_code_if_present(stock_code: str) -> str:
    """
    Extract OCC code if present in mixed format.
    
    Example: "SBET 260116 41.00P SBET260116P41000" → "SBET260116P41000"
    
    Args:
        stock_code: Original stock code from broker
        
    Returns:
        Extracted OCC code if found, otherwise original code
    """
    if not stock_code or not isinstance(stock_code, str):
        return stock_code
    
    # Pattern: TICKER + 6 digits + C/P + 5 digits (OCC format)
    match = re.search(r'([A-Z]+\d{6}[CP]\d{5})', stock_code)
    if match:
        extracted = match.group(1)
        if extracted != stock_code:
            logger.debug(f"Extracted OCC code from mixed format: '{stock_code}' → '{extracted}'")
        return extracted
    
    return stock_code


@dataclass
class ProcessedResult:
    """
    Simple data class for broker processing results
    Contains extracted cash and position data from broker statements
    """
    broker_name: str
    account_id: str
    cash_data: Dict[str, Union[float, str, None]]
    positions: List[Position]  # Changed from List[Dict] to List[Position]
    usd_total: float = 0.0
    position_values: Dict[str, Any] = None
    total_position_value_usd: float = 0.0
    statement_date: Optional[str] = None
    
    def __post_init__(self):
        if self.position_values is None:
            self.position_values = {}


class BrokerStatementProcessor:
    """
    Core processor for broker statement data extraction and processing.
    Orchestrates PDF conversion, image processing, and data extraction workflow.
    """
    
    def __init__(self):
        """Initialize the processor with PDF, LLM, price fetcher and excel processor instances."""
        self.llm_handler = LLMHandler()
        self.pdf_processor = PDFProcessor(self.llm_handler)
        self.excel_parser = ExcelPositionParser()
        self.price_fetcher = PriceFetcher()
    
    def process_folder(self, broker_folder: str, image_output_folder: str, 
                      date: str = None, broker: str = None, force: bool = False, 
                      max_workers: int = 10, skip_logging_setup: bool = False) -> Tuple[Optional[List], Optional[dict], Optional[str]]:
        """
        Process broker folder with complete workflow:
        1. Validate date format
        2. Setup logging
        3. Check existing images
        4. Convert PDFs to images
        5. Get exchange rates
        6. Process images and extract data
        7. Generate summary report
        
        Args:
            broker_folder: Path to folder containing broker PDF statements
            image_output_folder: Output folder for converted images
            date: Date string in YYYY-MM-DD format
            broker: Specific broker to process, or None for all
            force: Force re-conversion of PDFs even if images exist
            max_workers: Maximum number of concurrent threads
            skip_logging_setup: If True, skip logging setup (used by TC mode)
            
        Returns:
            Tuple: (processed_results, exchange_rates, date) or (None, None, None) if processing fails
        """
        # Step 1: Validate date format
        if date is None or not validate_date_format(date):
            print(f"ERROR: Invalid date format: {date}. Expected YYYY-MM-DD")
            return None, None, None
        
        # Step 2: Setup logging (skip if called from TC mode)
        if not skip_logging_setup:
            setup_logging(settings.LOG_DIR, date)
        
        # Step 3: Log processing start
        logger.info(f"Starting folder processing: {broker_folder}")
        if broker:
            logger.info(f"Processing specific broker: {broker}")
        logger.info(f"Using date: {date}")
        
        # Step 4: Use broker folder directly (no date subfolder structure)
        logger.info("Note: Using direct PDF processing (no image conversion needed)")
        
        # Ensure the broker folder exists
        if not Path(broker_folder).exists():
            logger.warning(f"Broker folder does not exist: {broker_folder}")
            return None, None, None
        
        # Step 7: Get exchange rates
        logger.info("Fetching exchange rate data...")
        try:
            exchange_rates = exchange_handler.get_rates_legacy(date)
            logger.success(f"Exchange rates retrieved: CNY={exchange_rates['CNY']}, HKD={exchange_rates['HKD']}")
        except Exception as e:
            logger.error(f"Failed to fetch exchange rates: {e}")
            return None, None, None
        
        # Step 8: Process PDFs directly
        logger.info("Processing PDFs directly...")
        
        # Step 9: Process all PDFs in broker folder with concurrency
        pdf_results = self._process_broker_pdfs(broker_folder, exchange_rates, broker, date, max_workers, force)
        
        # Step 11: Process Excel data from broker folder
        logger.info("Processing Excel data...")
        excel_results = self._process_excel_data(broker_folder, date, exchange_rates, broker)
        
        # Step 12: Merge PDF and Excel results
        merged_results = self._merge_position_data(pdf_results, excel_results)
        
        # Step 13: Optimize cross-broker position pricing
        if merged_results:
            logger.info("Optimizing cross-broker position pricing...")
            self._optimize_cross_broker_pricing(merged_results, date, exchange_rates)
        
        # Step 14: Generate complete asset summary
        if merged_results:
            print_asset_summary(merged_results, date)
        
        logger.info("All data processing completed!")
        
        # Return results for persistence
        return merged_results, exchange_rates, date
    
    def _process_excel_data(self, broker_folder: str, date: str, exchange_rates: dict, broker_filter: str = None) -> List[ProcessedResult]:
        """
        Process Excel position data from broker folder.
        
        Args:
            broker_folder: Path to broker folder containing Excel files
            date: Processing date
            exchange_rates: Exchange rate data
            broker_filter: Optional broker name filter (e.g., 'IB', 'MS')
            
        Returns:
            List of ProcessedResult objects with Excel position data
        """
        try:
            # 检测归档模式并传递给 Excel parser
            archive_mode = self._is_archive_mode(broker_folder)
            
            # Parse Excel data using ExcelPositionParser
            excel_data = self.excel_parser.parse_directory(
                broker_folder, 
                target_date=date,
                archive_mode=archive_mode
            )
            
            if not excel_data:
                logger.info("No Excel data found in broker folder")
                return []
            
            results = []
            
            # Convert Excel data to ProcessedResult format
            for broker_name, broker_payload in excel_data.items():
                # Apply broker filter if specified
                if broker_filter and broker_name.upper() != broker_filter.upper():
                    logger.info(f"Skipping {broker_name} - not matching filter '{broker_filter}'")
                    continue
                    
                positions = broker_payload.get("positions", [])
                statement_date = broker_payload.get("statement_date") or date
                logger.info(f"Processing {len(positions)} Excel positions for {broker_name}")
                
                # Create ProcessedResult for Excel data
                # Note: Excel data typically doesn't contain cash, only positions
                excel_result = ProcessedResult(
                    broker_name=broker_name,
                    account_id='EXCEL',  # Mark as Excel source
                    cash_data={'Total': 0.0, 'Total_type': 'USD'},  # No cash in Excel
                    positions=positions,
                    usd_total=0.0,  # No cash
                    statement_date=statement_date
                )
                
                # Calculate position values using PriceFetcher
                position_values = self.price_fetcher.calculate_position_values(
                    positions, date
                )
                excel_result.position_values = position_values
                excel_result.total_position_value_usd = position_values.get('total_value_usd', 0.0)
                
                results.append(excel_result)
                logger.success(f"Excel data processed for {broker_name}: {len(positions)} positions, ${excel_result.total_position_value_usd:,.2f} total value")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to process Excel data: {e}")
            return []
    
    def _merge_position_data(self, pdf_results: List[ProcessedResult], 
                           excel_results: List[ProcessedResult]) -> List[ProcessedResult]:
        """
        Merge PDF and Excel position data.
        
        Strategy: Keep all PDF results as-is (they contain cash data).
        Add Excel results as separate brokers to avoid conflicts.
        
        Args:
            pdf_results: Results from PDF processing
            excel_results: Results from Excel processing
            
        Returns:
            Merged list of ProcessedResult objects
        """
        merged = []
        
        # Add all PDF results
        if pdf_results:
            merged.extend(pdf_results)
            logger.info(f"Added {len(pdf_results)} PDF broker results")
        
        # Add all Excel results
        if excel_results:
            merged.extend(excel_results)
            logger.info(f"Added {len(excel_results)} Excel broker results")
        
        logger.success(f"Data merge completed: {len(merged)} total broker accounts")
        return merged
    
    def _optimize_cross_broker_pricing(self, results: List, date: str, exchange_rates: dict) -> None:
        """
        Optimize pricing by aggregating positions across brokers and batch querying prices.
        This replaces individual price queries with a single batch query for efficiency.
        """
        # Step 1: Aggregate all unique stock codes across brokers
        unique_symbols = {}  # symbol -> list of (broker_result, position_index)
        total_positions = 0
        
        for broker_result in results:
            for i, position in enumerate(broker_result.positions):
                stock_code = position.stock_code
                if stock_code not in unique_symbols:
                    unique_symbols[stock_code] = []
                unique_symbols[stock_code].append((broker_result, i))
                total_positions += 1
        
        logger.info(f"Found {len(unique_symbols)} unique stocks across {total_positions} positions")
        
        # Step 2: Batch query prices for all unique symbols
        optimized_prices = {}  # symbol -> {'price': float, 'source': str, 'currency': str}
        
        for symbol in unique_symbols.keys():
            try:
                logger.debug(f"Querying price for {symbol}...")
                # Get raw_description from first position with this symbol for better option parsing
                first_position = unique_symbols[symbol][0][0].positions[unique_symbols[symbol][0][1]]
                raw_description = first_position.raw_description
                
                # get_stock_price now returns (price, currency) tuple
                price, api_currency = get_stock_price(symbol, date, settings.PRICE_SOURCE, raw_description)
                
                if price is not None and price > 0.0 and api_currency:
                    # Use API-provided currency (determined by API type: US vs HK)
                    optimized_prices[symbol] = {
                        'price': price,
                        'source': settings.PRICE_SOURCE.title(),  # 'Futu' or 'Akshare'
                        'currency': api_currency  # Use currency from API (USD for US, HKD for HK)
                    }
                    logger.debug(f"Got price for {symbol}: ${price} {api_currency}")
                else:
                    logger.debug(f"No price available for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to get price for {symbol}: {e}")
                import traceback
                logger.debug(f"Exception details for {symbol}: {traceback.format_exc()}")
        
        logger.success(f"Batch queried {len(optimized_prices)}/{len(unique_symbols)} stock prices")
        
        # Step 3: Update all position data with batch-queried prices
        for symbol, price_data in optimized_prices.items():
            for broker_result, position_index in unique_symbols[symbol]:
                # Update the position with optimized price data
                position = broker_result.positions[position_index]
                position.final_price = price_data['price']
                position.final_price_source = price_data['source']
                position.optimized_price_currency = price_data['currency']
        
        # Step 4: Recalculate position values for each broker using optimized prices
        for broker_result in results:
            if not broker_result.positions:
                continue
                
            total_position_value = 0.0
            successful_prices = 0
            
            for position in broker_result.positions:
                holding = position.holding
                # Ensure holding is numeric
                try:
                    holding_num = int(holding) if isinstance(holding, (int, float)) else int(float(str(holding).replace(',', '')))
                except (ValueError, TypeError):
                    holding_num = 0
                
                # Priority: final_price (from optimization) > broker_price
                final_price = position.final_price or position.broker_price
                price_source = position.final_price_source if position.final_price else 'Broker'
                price_currency = position.optimized_price_currency if position.final_price else position.price_currency
                
                if final_price is not None:
                    # Apply correct multiplier based on instrument type
                    stock_code = position.stock_code
                    raw_description = position.raw_description
                    broker_multiplier = position.multiplier
                    
                    multiplier = get_option_multiplier(stock_code, raw_description, broker_multiplier)
                    position_value = final_price * holding_num * multiplier
                    
                    if multiplier > 1:
                        logger.debug(f"Applied {multiplier}x option multiplier for {stock_code}: {holding_num} × {final_price} × {multiplier} = {position_value}")
                    else:
                        logger.debug(f"Stock/OTC calculation for {stock_code}: {holding_num} × {final_price} = {position_value}")
                    
                    total_position_value += position_value
                    successful_prices += 1
                    
                    # Update position with final calculation results
                    position.final_price = final_price
                    position.final_price_source = price_source
                    position.optimized_price_currency = price_currency
                    # Note: PositionValueUSD is not stored in Position object,
                    # only used for aggregated calculation
            
            # Update broker result with recalculated values
            broker_result.total_position_value_usd = total_position_value
            if not broker_result.position_values:
                broker_result.position_values = {}
            broker_result.position_values['successful_prices'] = successful_prices
            broker_result.position_values['failed_prices'] = len(broker_result.positions) - successful_prices
            broker_result.position_values['total_value_usd'] = total_position_value
            
            logger.info(f"Updated {broker_result.broker_name}: ${total_position_value:,.2f} USD "
                      f"({successful_prices}/{len(broker_result.positions)} stocks priced)")
        
        logger.success("Cross-broker pricing optimization completed")
    
    def _is_archive_mode(self, broker_folder: str) -> bool:
        """
        检测是否为归档模式（通过路径判断）
        归档模式：路径包含 'archives'
        """
        return 'archives' in Path(broker_folder).parts
    
    def _extract_archive_date(self, filename: str, broker: str) -> Optional[str]:
        """
        提取归档文件名中的日期，格式 {BROKER}_{YYYY-MM-DD}_{ID}.ext
        返回 YYYY-MM-DD 字符串或 None
        """
        pattern = rf"{re.escape(broker)}_(\d{{4}}-\d{{2}}-\d{{2}})_.*"
        match = re.match(pattern, filename, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _broker_has_excel_archives(self, broker_dir: Path) -> bool:
        """
        Check if broker archive directory contains Excel files (used to downgrade missing PDF warnings).
        """
        excel_patterns = ["*.xls", "*.xlsx", "*.XLS", "*.XLSX"]
        for pattern in excel_patterns:
            if any(broker_dir.glob(pattern)):
                return True
        return False
    
    def _process_broker_pdfs(self, pdf_root: str, exchange_rates: dict, broker_filter: str = None, date: str = None, max_workers: int = 10, force: bool = False) -> List[ProcessedResult]:
        """
        Process all PDFs in broker folder using concurrent processing
        
        Args:
            pdf_root: Root directory containing broker PDF files
            exchange_rates: Exchange rate data
            broker_filter: Optional broker filter
            date: Processing date
            max_workers: Maximum number of concurrent workers
            
        Returns:
            List of ProcessedResult objects
        """
        pdf_root_path = Path(pdf_root)
        
        if not pdf_root_path.exists():
            logger.warning(f"PDF root directory does not exist: {pdf_root}")
            return []
        
        # 检测归档模式
        archive_mode = self._is_archive_mode(pdf_root)
        if archive_mode:
            logger.info("📦 Using ARCHIVE mode (file name based filtering)")
        else:
            logger.info("📁 Using STATEMENT mode (directory based structure)")
        
        # Collect all PDF processing tasks
        pdf_tasks = []
        
        for broker_dir in pdf_root_path.iterdir():
            if not broker_dir.is_dir():
                continue
            
            broker_name = broker_dir.name

            # Skip folders not representing brokers (temp uploads, TC storage, etc.)
            if broker_name.lower() in {'temp', 'tradeconfirmation'}:
                logger.debug(f"Skipping non-broker directory: {broker_name}")
                continue
            
            # Apply broker filter
            if broker_filter and broker_name.upper() != broker_filter.upper():
                continue
            
            # 根据模式选择不同的文件查找逻辑
            pdf_files = []
            
            if archive_mode:
                # 归档模式：从券商目录查找匹配日期的文件
                if not date:
                    logger.error(f"Archive mode requires --date parameter")
                    raise ValueError("Archive mode requires date parameter")
                
                # 查找最接近 target_date 的 PDF
                all_pdfs = list(broker_dir.glob("*.pdf"))
                dated_files = []
                for pdf_file in all_pdfs:
                    matched_date = self._extract_archive_date(pdf_file.name, broker_name)
                    if matched_date and matched_date <= date:
                        dated_files.append((matched_date, pdf_file))
                
                if not dated_files:
                    if self._broker_has_excel_archives(broker_dir):
                        logger.info(f"No archived PDFs for {broker_name}; Excel files will be used instead")
                    else:
                        logger.warning(f"No archived PDF files found for {broker_name} on or before {date}")
                        logger.warning(f"Expected filename pattern: {broker_name}_YYYY-MM-DD_*.pdf")
                    continue
                
                # 选择最接近 target_date 的文件
                matched_date, pdf_file = max(dated_files, key=lambda x: x[0])
                if matched_date != date:
                    logger.info(
                        f"{broker_name}: no {date} statement found; using nearest {matched_date}"
                    )
                pdf_files.append(pdf_file)
                statement_date = matched_date
                    
            else:
                # Statement模式：原有逻辑
                # Determine search paths (prefer date-specific folder if available)
                search_paths = []
                if date:
                    date_dir = broker_dir / date
                    if date_dir.exists():
                        search_paths.append(date_dir)
                
                if not search_paths:
                    search_paths.append(broker_dir)

                # Find PDF files (support nested date folders)
                for path in search_paths:
                    pdf_files.extend(
                        p for p in path.rglob("*.pdf")
                        if p.is_file() and "__MACOSX" not in p.parts
                    )

                if not pdf_files:
                    logger.info(f"No PDF files found for {broker_name}")
                    continue
                statement_date = date
            
            logger.info(f"Found {len(pdf_files)} PDF files for {broker_name}")
            
            # Add each PDF file as a task
            for pdf_file in pdf_files:
                pdf_tasks.append({
                    'pdf_file': pdf_file,
                    'broker_name': broker_name,
                    'exchange_rates': exchange_rates,
                    'date': date,
                    'force': force,
                    'statement_date': statement_date
                })
        
        if not pdf_tasks:
            logger.warning("No PDF tasks found to process")
            return []
        
        logger.info(f"Starting concurrent PDF processing: {len(pdf_tasks)} tasks with {max_workers} workers")
        
        # Process PDFs concurrently
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(self._process_single_pdf_task, task): task
                for task in pdf_tasks
            }
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                completed += 1
                
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        logger.success(f"✅ [{completed}/{len(pdf_tasks)}] {task['broker_name']}/{result.account_id} processed")
                    else:
                        logger.warning(f"⚠️ [{completed}/{len(pdf_tasks)}] {task['broker_name']} processing failed")
                        
                except Exception as e:
                    logger.error(f"❌ [{completed}/{len(pdf_tasks)}] {task['pdf_file'].name} failed: {e}")
        
        logger.info(f"🎉 Concurrent PDF processing completed: {len(results)}/{len(pdf_tasks)} successful")
        return results

    @staticmethod
    def _normalize_holding_value(value: Union[str, int, float, None]) -> float:
        """
        Normalize broker-provided holding quantity into a float.
        
        PDF outputs sometimes contain comma-separated strings; downstream logic expects numbers.
        """
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(',', ''))
            except ValueError:
                logger.warning(f"Unexpected holding format '{value}', defaulting to 0")
                return 0.0
        return 0.0
    
    def _process_single_pdf_task(self, task: Dict[str, Any]) -> Optional[ProcessedResult]:
        """
        Process a single PDF task (used for concurrent processing)
        
        Args:
            task: Dictionary containing pdf_file, broker_name, exchange_rates, date
            
        Returns:
            ProcessedResult object if successful, None otherwise
        """
        pdf_file = task['pdf_file']
        broker_name = task['broker_name']
        exchange_rates = task['exchange_rates']
        date = task['date']
        force = task.get('force', False)
        statement_date = task.get('statement_date') or date
        
        try:
            # Process PDF with PDFProcessor
            pdf_result = self.pdf_processor.process_pdf(pdf_file, broker_name, force=force)
            
            if pdf_result['status'] != 'success':
                logger.error(f"PDF processing failed for {pdf_file.name}: {pdf_result.get('error', 'Unknown error')}")
                return None
            
            # Convert PDF result to ProcessedResult format
            data = pdf_result['data']
            
            # Calculate USD total from cash data
            usd_total = self._calculate_usd_total(data.get('Cash', {}), exchange_rates)
            
            # Convert PDF position format to Position objects
            position_dicts = data.get('Positions', [])
            position_list = []
            for pos_dict in position_dicts:
                # Extract OCC code if present in mixed format
                stock_code = pos_dict.get('StockCode', '')
                if stock_code and ' ' in stock_code and re.search(r'\d{6}[CP]\d{5}', stock_code):
                    stock_code = extract_occ_code_if_present(stock_code)

                holding_value = self._normalize_holding_value(pos_dict.get('Holding', 0))
                
                # Create Position object
                pos = Position(
                    stock_code=stock_code,
                    holding=holding_value,
                    broker_price=pos_dict.get('Price'),
                    raw_description=pos_dict.get('Description'),
                    price_currency=pos_dict.get('PriceCurrency'),
                    multiplier=pos_dict.get('Multiplier'),
                    broker=broker_name,
                    context=PositionContext.BASE
                )
                position_list.append(pos)
            
            processed_result = ProcessedResult(
                broker_name=broker_name,
                account_id=pdf_result['account_id'],
                cash_data=data.get('Cash', {}),
                positions=position_list,
                usd_total=usd_total,
                statement_date=statement_date
            )
            
            # Position values will be calculated later in _optimize_cross_broker_pricing
            # to avoid redundant API calls and enable batch pricing optimization
            
            return processed_result
            
        except Exception as e:
            logger.error(f"Error in PDF task processing for {pdf_file.name}: {e}")
            return None
    
    def _calculate_usd_total(self, cash_data: dict, exchange_rates: dict) -> float:
        """Calculate total cash value in USD"""
        try:
            total = 0.0
            
            usd = cash_data.get('USD', 0) or 0
            hkd = cash_data.get('HKD', 0) or 0
            cny = cash_data.get('CNY', 0) or 0
            
            total += float(usd)
            
            # Convert HKD to USD
            if hkd:
                if 'HKD' not in exchange_rates:
                    logger.warning("HKD exchange rate not available, skipping HKD conversion")
                else:
                    total += float(hkd) * exchange_rates['HKD']  # HKD→USD rate is direct multiplier
            
            # Convert CNY to USD
            if cny:
                if 'CNY' not in exchange_rates:
                    logger.warning("CNY exchange rate not available, skipping CNY conversion")
                else:
                    total += float(cny) * exchange_rates['CNY']  # CNY→USD rate is direct multiplier
            
            return total
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.warning(f"Error calculating USD total: {e}")
            return 0.0
    
