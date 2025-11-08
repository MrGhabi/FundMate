"""
Trade Confirmation Processor
Incremental portfolio update based on trade confirmation files.

All comments in English as per requirement.
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import pandas as pd
from pathlib import Path
from loguru import logger
import re
from datetime import datetime

try:
    from .broker_processor import ProcessedResult
    from .price_fetcher import PriceFetcher, get_stock_price
    from .data_persistence import DataPersistence, save_processing_results
    from .exchange_rate_handler import exchange_handler
    from .utils import calculate_position_value, get_option_multiplier
    from .hk_option_price_helper import parse_hk_option_description
    from .us_option_price_helper import parse_us_option_description
    from .config import settings
except (ImportError, ValueError):
    from broker_processor import ProcessedResult
    from price_fetcher import PriceFetcher, get_stock_price
    from data_persistence import DataPersistence, save_processing_results
    from exchange_rate_handler import exchange_handler
    from utils import calculate_position_value, get_option_multiplier
    from hk_option_price_helper import parse_hk_option_description
    from us_option_price_helper import parse_us_option_description
    from config import settings


@dataclass
class Transaction:
    """
    Trade transaction record parsed from Excel.
    Represents a single buy/sell transaction.
    """
    date: str              # YYYY-MM-DD
    broker: str            # HTI, TF, etc.
    stock_code: str        # 9988 HK, TSLA, etc.
    direction: str         # BUY/SELL
    quantity: int          # Number of shares
    avg_price: float       # Average execution price
    amount_usd: float      # USD amount (cash impact)
    currency: str          # Original currency (HKD, USD, etc.)
    market: str            # Market/Exchange (HK, US, etc.)


class TradeConfirmationProcessor:
    """
    Trade Confirmation Processor - Incremental Portfolio Update
    
    Uses trade confirmation files to update portfolio positions and cash
    from a base date to a target date.
    """
    
    def __init__(self):
        """Initialize processor with existing components"""
        self.price_fetcher = PriceFetcher()
        self.persistence = DataPersistence()
        self.price_failures = []  # Track failed price fetches
        self._hk_code_cache: Dict[str, str] = {}
    
    def resolve_hk_numeric_to_hkats(self, numeric_code: str) -> str:
        """
        Resolve HK numeric stock code (e.g., 2628) to HKATS letter code via Futu option chain.

        Args:
            numeric_code: Numeric HK code from TC file, with or without HK. prefix

        Returns:
            HKATS letter code (e.g., CLI)

        Raises:
            ValueError: When input is invalid
            RuntimeError: When Futu API cannot provide mapping
        """
        if not numeric_code:
            raise ValueError("Empty HK numeric code cannot be resolved")

        code = numeric_code.strip().upper()
        if code.startswith('HK.'):
            code = code[3:]

        if not code.isdigit():
            raise ValueError(
                f"Expected HK numeric code (digits only), got '{numeric_code}'"
            )

        normalized_key = f"{int(code):05d}"
        if normalized_key in self._hk_code_cache:
            return self._hk_code_cache[normalized_key]

        try:
            import futu as ft
        except ImportError as exc:
            raise RuntimeError(
                "Futu SDK is not installed; cannot resolve HK numeric code to HKATS"
            ) from exc

        futu_code = f"HK.{normalized_key}"

        try:
            quote_ctx = ft.OpenQuoteContext(
                host=settings.FUTU_HOST,
                port=settings.FUTU_PORT
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to Futu OpenD for HK code resolution: {exc}"
            ) from exc

        try:
            ret, data = quote_ctx.get_option_chain(
                code=futu_code,
                index_option_type=ft.IndexOptionType.NORMAL
            )
        finally:
            quote_ctx.close()

        if ret != ft.RET_OK or data is None or data.empty:
            logger.warning(
                f"No option chain found for HK code '{numeric_code}' - keeping original numeric code"
            )
            return numeric_code.strip().lstrip('0') or '0'

        option_code = data.iloc[0].get('code')
        if not isinstance(option_code, str) or not option_code.startswith('HK.'):
            raise RuntimeError(
                f"Unexpected option code format returned by Futu for '{numeric_code}': {option_code}"
            )

        match = re.match(r'^HK\.([A-Z]+)', option_code)
        if not match:
            raise RuntimeError(
                f"Failed to extract HKATS code from Futu option '{option_code}'"
            )

        hkats_code = match.group(1)
        self._hk_code_cache[normalized_key] = hkats_code

        logger.info(
            f"HK numeric code mapped via Futu option chain: {normalized_key} → {hkats_code}"
        )

        return hkats_code

    def standardize_option_format(self, stock_code: str) -> str:
        """
        Standardize TC option format to OCC
        
        Handles:
          1. "TICKER US MM/DD/YY C/P STRIKE" (US format)
          2. "TICKER HK MM/DD/YY C/P STRIKE" (HK format)
        
        Examples:
          - "SBET US 01/16/26 P41" → "SBET260116P41000"
          - "2628 HK 06/29/26 C20" → "2628260629C20000"
        
        Args:
            stock_code: Stock code from TC file
            
        Returns:
            Standardized code (OCC format for options)
            
        Raises:
            ValueError: If option format is unrecognized
        """
        if not stock_code:
            return stock_code
        
        # Remove trailing " Equity" or " Option"
        stock_code = re.sub(r'\s+(Equity|Option)$', '', stock_code, flags=re.IGNORECASE).strip()
        
        # Check 1: Already OCC format? (TICKER + 6 digits + C/P + 5 digits)
        if re.match(r'^[A-Z0-9]+\d{6}[CP]\d{5}$', stock_code):
            return stock_code
        
        # Check 2: TC format? "[PREFIX] TICKER MARKET MM/DD/YY C/P STRIKE"
        # MARKET can be: US, HK, SS, C1, etc. (2 alphanumeric chars)
        # PREFIX is optional (e.g., "GS" in "GS 3690 HK 05/28/27 C180")
        match = re.search(
            r'^(?:[A-Z]{2}\s+)?([A-Z0-9]+)\s+([A-Z0-9]{2})\s+(\d{2})/(\d{2})/(\d{2})\s+([CP])(\d+)$',
            stock_code
        )
        
        if match:
            ticker, market, mm, dd, yy, cp, strike = match.groups()
            market_upper = market.upper()

            # Convert HK numeric code to HKATS letter code via Futu API
            if ticker.isdigit() and market_upper in ('HK', 'C1'):
                ticker = self.resolve_hk_numeric_to_hkats(ticker)

            occ_code = f"{ticker}{yy}{mm}{dd}{cp}{int(strike)*1000:05d}"
            logger.info(f"TC option standardized ({market}): '{stock_code}' → '{occ_code}'")
            return occ_code
        
        # Check 3: No date pattern? Not an option, likely a stock
        # Options must have date pattern MM/DD/YY
        if not re.search(r'\d{2}/\d{2}/\d{2}', stock_code):
            # No date pattern - likely a stock ticker like "1263 HK", "AAPL", etc.
            return stock_code
        
        # Unknown option format - FAIL FAST
        # (has date pattern but doesn't match known formats)
        raise ValueError(
            f"Unrecognized option format in TC file: '{stock_code}'\n"
            f"Expected formats:\n"
            f"  - '[PREFIX] TICKER MARKET MM/DD/YY C/P STRIKE'\n"
            f"    Examples: 'SBET US 01/16/26 P41', '2628 HK 06/29/26 C20', 'GS 3690 HK 05/28/27 C180'\n"
            f"  - OCC: 'TICKER + 6digits + C/P + 5digits' (e.g., 'SBET260116P41000')\n"
            f"Please check TC file and standardize the format."
        )
    
    def process_with_trade_confirmation(
        self,
        base_broker_folder: str,
        base_date: str,
        target_date: str,
        tc_folder: str = "data/archives/TradeConfirmation"
    ) -> Tuple[List[ProcessedResult], Dict, str]:
        """
        End-to-end TC processing: Reprocess base statements + apply TC + update prices.
        
        Args:
            base_broker_folder: Broker folder containing base_date statements
            base_date: Base date to start from (e.g., "2025-07-18")
            target_date: Target date to update to (e.g., "2025-07-22")
            tc_folder: Folder containing standardized TC-{YYYY-MM-DD}-*.xlsx files
            
        Returns:
            (results, exchange_rates, date) - Same format as normal mode
        """
        logger.info("=" * 80)
        logger.info("PHASE 1: Processing Base Portfolio")
        logger.info("=" * 80)
        
        # Reprocess base statements from broker folder
        from broker_processor import BrokerStatementProcessor
        
        processor = BrokerStatementProcessor()
        base_results, base_exchange_rates, _ = processor.process_folder(
            broker_folder=base_broker_folder,
            image_output_folder=settings.pictures_dir,
            date=base_date,
            broker=None,
            force=False,
            max_workers=10,
            skip_logging_setup=True  # Don't create separate log file
        )
        
        if not base_results or not base_exchange_rates:
            raise ValueError(f"Failed to process base statements for {base_date}")
        
        logger.success(f"Base portfolio processed: {len(base_results)} brokers, date={base_date}")
        
        logger.info("=" * 80)
        logger.info("PHASE 2: Applying Trade Confirmations")
        logger.info("=" * 80)
        
        # Parse trade confirmations (expects standardized filenames)
        transactions = self._parse_trade_confirmations(
            tc_folder, base_date, target_date
        )
        logger.info(f"Parsed {len(transactions)} transactions from TC files")
        
        # Fail if no transactions found
        if len(transactions) == 0:
            raise ValueError(
                f"No transactions found in date range!\n"
                f"Base date: {base_date} (exclusive)\n"
                f"Target date: {target_date} (inclusive)\n"
                f"Date range: ({base_date}, {target_date}]\n"
                f"\nPossible causes:\n"
                f"  1. No TC files in this date range\n"
                f"  2. All TC files have format errors\n"
                f"  3. Base date >= Target date (invalid range)\n"
                f"  4. TC files exist but contain no valid transaction rows"
            )
        
        # Apply transactions to base results
        updated_results = self._apply_transactions(
            base_results, transactions
        )
        
        logger.info("=" * 80)
        logger.info("PHASE 3: Updating Prices to Target Date")
        logger.info("=" * 80)
        
        # Update prices to target date
        target_exchange_rates = exchange_handler.get_rates_legacy(target_date)
        self._update_prices(updated_results, target_date, target_exchange_rates)
        
        # Generate report
        self._generate_update_report(
            base_date, target_date, transactions, updated_results
        )
        
        logger.success(f"TC processing completed: {base_date} → {target_date}")
        
        return updated_results, target_exchange_rates, target_date
    
    def _parse_trade_confirmations(
        self, 
        tc_folder: str, 
        start_date: str, 
        end_date: str
    ) -> List[Transaction]:
        """
        Parse trade confirmation Excel files in date range.
        Expects standardized filename format: TC-{YYYY-MM-DD}-*.xlsx
        
        Args:
            tc_folder: Folder containing TC files
            start_date: Start date (exclusive) in YYYY-MM-DD format
            end_date: End date (inclusive) in YYYY-MM-DD format
            
        Returns:
            List of Transaction objects
        """
        folder = Path(tc_folder)
        transactions = []
        
        if not folder.exists():
            logger.warning(f"TC folder does not exist: {tc_folder}")
            return []
        
        # Find all TC files
        tc_files = sorted(folder.glob("TC-*.xlsx"))
        
        if not tc_files:
            raise FileNotFoundError(
                f"No trade confirmation files found!\n"
                f"Folder: {tc_folder}\n"
                f"Expected filename pattern: TC-YYYY-MM-DD-*.xlsx\n"
                f"\nPlease check:\n"
                f"  1. Folder path is correct\n"
                f"  2. Files have been preprocessed with: python src/scripts/rename_trade_confirmations.py --execute\n"
                f"  3. Files exist in the folder"
            )
        
        logger.info(f"Found {len(tc_files)} TC files")
        
        all_transactions = []
        for tc_file in tc_files:
            logger.info(f"Processing TC file: {tc_file.name}")
            
            # Parse Excel file (now uses Trade Date from Excel)
            file_transactions = self._parse_tc_excel(tc_file, None)
            all_transactions.extend(file_transactions)
            
            logger.info(f"  Extracted {len(file_transactions)} transactions")
        
        # Filter transactions by Trade Date (start_date, end_date]
        transactions = [
            txn for txn in all_transactions
            if start_date < txn.date <= end_date
        ]
        
        logger.info(
            f"Filtered {len(transactions)}/{len(all_transactions)} transactions "
            f"in date range ({start_date}, {end_date}]"
        )
        
        return transactions
    
    def _extract_date_from_tc_filename(self, filename: str) -> str:
        """
        Extract date from standardized TC filename.
        Format: TC-{YYYY-MM-DD}-{original_name}.xlsx
        
        Args:
            filename: TC filename
            
        Returns:
            Date string in YYYY-MM-DD format
        """
        match = re.match(r'TC-(\d{4}-\d{2}-\d{2})-', filename)
        if match:
            return match.group(1)
        raise ValueError(f"Invalid TC filename format: {filename}")
    
    def _parse_tc_excel(self, file_path: Path, file_date: str) -> List[Transaction]:
        """
        Parse a single trade confirmation Excel file.
        
        Args:
            file_path: Path to Excel file
            file_date: Date extracted from filename
            
        Returns:
            List of Transaction objects
        """
        try:
            # Try reading normally first
            df = pd.read_excel(file_path)
            
            # Check if first row contains column names (header in first data row)
            if 'Unnamed' in str(df.columns[0]):
                # Try header=1 first (common for US TC files)
                df_header1 = pd.read_excel(file_path, header=1)
                if 'Trade Date' in df_header1.columns:
                    df = df_header1
                else:
                    # Fallback to header=0 and check first row
                    df = pd.read_excel(file_path, header=0)
                    if len(df) > 0 and df.iloc[0].astype(str).str.contains('Trade Date', na=False).any():
                        df = df.iloc[1:].reset_index(drop=True)
            
            # Validate required columns
            required_cols = [
                'Trade Date', 'Stock Code', 'BUY/SELL', 'Quantity',
                'Avg. Price', 'Amount (USD)', 'Broker', 'Currency'
            ]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise ValueError(
                    f"\n{'='*60}\n"
                    f"INVALID TRADE CONFIRMATION FILE FORMAT\n"
                    f"{'='*60}\n"
                    f"File: {file_path.name}\n"
                    f"Missing required columns: {missing_cols}\n"
                    f"Available columns: {list(df.columns)}\n"
                    f"\nFirst 5 rows of data:\n{df.head()}\n"
                    f"{'='*60}\n"
                    f"Please fix the Excel file format before processing.\n"
                )
            
            transactions = []
            
            for _, row in df.iterrows():
                # Skip empty rows
                if pd.isna(row['Stock Code']):
                    continue
                
                # Use Trade Date from Excel, not filename date
                trade_date = pd.to_datetime(row['Trade Date']).strftime('%Y-%m-%d')
                
                # Normalize direction: remove spaces (e.g., "BUY COVER" -> "BUYCOVER")
                direction = str(row['BUY/SELL']).strip().upper().replace(' ', '')
                
                # Clean stock code: remove Bloomberg suffixes
                stock_code = str(row['Stock Code']).strip()
                
                # Step 1: Remove ' Equity' suffix (Bloomberg format)
                stock_code = stock_code.replace(' Equity', '')
                
                # Step 2: Intelligently remove ' US' suffix
                # Keep ' US' for options, remove for pure stocks
                if stock_code.endswith(' US'):
                    # Check if this is an option (contains date pattern or option keywords)
                    is_option = (
                        re.search(r'\d{2}/\d{2}/\d{2}', stock_code) or  # Date format MM/DD/YY
                        'PUT' in stock_code.upper() or 
                        'CALL' in stock_code.upper() or
                        re.search(r'\s+[CP]\d+', stock_code)  # Pattern like P15, C300
                    )
                    if not is_option:
                        # Pure stock, remove ' US' suffix
                        stock_code = stock_code[:-3].strip()
                
                stock_code = stock_code.strip()
                
                # Standardize option format to OCC (e.g., "SBET US 01/16/26 P41" → "SBET260116P41000")
                stock_code = self.standardize_option_format(stock_code)
                
                # Normalize Amount to absolute value for consistent processing
                # TC files may have signed (US) or unsigned (Asia) amounts
                transaction = Transaction(
                    date=trade_date,
                    broker=str(row['Broker']).strip(),
                    stock_code=stock_code,
                    direction=direction,
                    quantity=int(row['Quantity']),
                    avg_price=float(row['Avg. Price']),
                    amount_usd=abs(float(row['Amount (USD)'])),
                    currency=str(row['Currency']).strip(),
                    market=str(row.get('Market/Exchange', '')).strip()
                )
                
                transactions.append(transaction)
            
            return transactions
            
        except ValueError:
            # Re-raise ValueError with our custom message
            raise
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse trade confirmation file: {file_path.name}\n"
                f"Error: {type(e).__name__}: {e}\n"
                f"Please check the file format and content."
            ) from e
    
    def _apply_transactions(
        self, 
        base_results: List[ProcessedResult],
        transactions: List[Transaction]
    ) -> List[ProcessedResult]:
        """
        Apply transactions to base portfolio.
        
        Args:
            base_results: Base portfolio results
            transactions: List of transactions to apply
            
        Returns:
            Updated portfolio results
        """
        logger.info("Applying transactions to base portfolio...")
        
        # Group transactions by broker (case-insensitive)
        broker_txns = {}
        for txn in transactions:
            broker_key = txn.broker.strip().upper()  # Normalize to uppercase
            if broker_key not in broker_txns:
                broker_txns[broker_key] = []
            broker_txns[broker_key].append(txn)
        
        # Apply transactions to each broker (case-insensitive matching)
        for result in base_results:
            broker_key = result.broker_name.strip().upper()  # Normalize to uppercase
            
            if broker_key in broker_txns:
                txns = broker_txns[broker_key]
                logger.info(f"Applying {len(txns)} transactions to {result.broker_name}")
                self._apply_broker_transactions(result, txns)
            else:
                logger.debug(f"No transactions for {result.broker_name}")
        
        return base_results
    
    def _apply_broker_transactions(
        self, 
        result: ProcessedResult, 
        transactions: List[Transaction]
    ):
        """
        Apply transactions to a single broker's portfolio.
        
        Args:
            result: ProcessedResult to update (modified in-place)
            transactions: Transactions for this broker
        """
        for txn in transactions:
            # Normalize SELLSHORT to SELL (both handled by _apply_sell)
            direction = txn.direction
            if direction == 'SELLSHORT':
                direction = 'SELL'
            
            if direction in ('BUY', 'BUYCOVER'):
                # BUYCOVER is treated as BUY (covering short position)
                self._apply_buy(result, txn)
            elif direction == 'SELL':
                self._apply_sell(result, txn)
            else:
                raise ValueError(
                    f"Unknown transaction direction: '{txn.direction}'\n"
                    f"Broker: {result.broker_name}\n"
                    f"Stock: {txn.stock_code}\n"
                    f"Quantity: {txn.quantity}\n"
                    f"Supported directions: BUY, BUYCOVER, SELL, SELLSHORT\n"
                    f"Please check the 'BUY/SELL' column in the TC file."
                )
    
    def _apply_buy(self, result: ProcessedResult, txn: Transaction):
        """
        Apply a BUY transaction: increase position, decrease cash.
        
        Args:
            result: ProcessedResult to update
            txn: Buy transaction
        """
        # Find or create position
        position = self._find_position(result.positions, txn.stock_code)
        
        if position:
            # Update existing position
            position['Holding'] += txn.quantity
        else:
            # Create new position
            # Calculate multiplier automatically (same logic as base mode)
            multiplier = get_option_multiplier(
                stock_code=txn.stock_code,
                raw_description=txn.stock_code,
                broker_multiplier=None
            )
            new_position = {
                'StockCode': txn.stock_code,
                'RawDescription': txn.stock_code,  # Will be updated with price fetch
                'Holding': txn.quantity,
                'BrokerPrice': txn.avg_price,
                'PriceCurrency': txn.currency,
                'FinalPrice': None,  # Will be updated later
                'FinalPriceSource': '',
                'OptimizedPriceCurrency': 'USD',
                'Multiplier': multiplier
            }
            result.positions.append(new_position)
            logger.debug(f"  Created new position with multiplier={multiplier} for {txn.stock_code}")
        
        # Decrease cash (USD)
        current_usd = result.cash_data.get('USD', 0) or 0
        result.cash_data['USD'] = current_usd - txn.amount_usd
        result.usd_total = result.usd_total - txn.amount_usd
        
        logger.debug(f"  BUY {txn.quantity} {txn.stock_code} @ ${txn.avg_price}")
    
    def _apply_sell(self, result: ProcessedResult, txn: Transaction):
        """
        Apply a SELL transaction: decrease position OR create short position, increase cash.
        
        Handles two scenarios:
        1. Sell to Close: Selling existing long position (quantity > 0)
        2. Sell to Open: Creating new short position (quantity < 0, "Sell Short")
        
        Args:
            result: ProcessedResult to update
            txn: Sell transaction
        """
        # Find position
        position = self._find_position(result.positions, txn.stock_code)
        
        # Check if this is a short sale (negative quantity)
        is_short_sale = txn.quantity < 0
        
        if is_short_sale:
            # Sell Short: Create or increase short position
            abs_quantity = abs(txn.quantity)
            
            if position:
                # Add to existing short position (make it more negative)
                position['Holding'] -= abs_quantity
            else:
                # Create new short position
                # Calculate multiplier automatically (same logic as base mode)
                multiplier = get_option_multiplier(
                    stock_code=txn.stock_code,
                    raw_description=txn.stock_code,
                    broker_multiplier=None
                )
                new_position = {
                    'StockCode': txn.stock_code,
                    'RawDescription': txn.stock_code,
                    'Holding': -abs_quantity,  # Negative for short
                    'BrokerPrice': txn.avg_price,
                    'PriceCurrency': txn.currency,
                    'FinalPrice': None,
                    'FinalPriceSource': '',
                    'OptimizedPriceCurrency': 'USD',
                    'Multiplier': multiplier
                }
                result.positions.append(new_position)
                logger.debug(f"  Created new short position with multiplier={multiplier} for {txn.stock_code}")
            
            logger.debug(f"  SELL SHORT {abs_quantity} {txn.stock_code} @ ${txn.avg_price}")
        else:
            # Normal sell: Close long position
            if position:
                # Update quantity
                position['Holding'] -= txn.quantity
                
                # Check for oversold (shouldn't happen in normal case)
                if position['Holding'] < 0:
                    raise ValueError(
                        f"SELL quantity exceeds current holding!\n"
                        f"Broker: {result.broker_name}\n"
                        f"Stock: {txn.stock_code}\n"
                        f"Current holding: {position['Holding'] + txn.quantity}\n"
                        f"SELL quantity: {txn.quantity}\n"
                        f"Resulting holding: {position['Holding']} (NEGATIVE!)\n"
                        f"This is not a 'Sell Short' (quantity should be negative for shorts).\n"
                        f"Please check the transaction data or base date."
                    )
                
                # Remove position if fully sold
                if position['Holding'] == 0:
                    result.positions.remove(position)
                    logger.debug(f"  Position {txn.stock_code} fully closed")
            else:
                raise ValueError(
                    f"SELL transaction for non-existent position!\n"
                    f"Broker: {result.broker_name}\n"
                    f"Stock: {txn.stock_code}\n"
                    f"SELL quantity: {txn.quantity}\n"
                    f"Price: ${txn.avg_price}\n"
                    f"Amount: ${txn.amount_usd} USD\n"
                    f"\nPossible causes:\n"
                    f"  1. Position not in base portfolio - check base_date\n"
                    f"  2. Stock code format mismatch (e.g., '2318 HK' vs '02318')\n"
                    f"  3. Wrong broker name in TC file\n"
                    f"  4. This is a 'Sell Short' but quantity is not negative\n"
                    f"\nCurrent positions in {result.broker_name}:\n"
                    f"  {[p['StockCode'] for p in result.positions]}\n"
                    f"\nNote: For short sales, quantity should be negative (e.g., -500)"
                )
        
        # Increase cash (USD)
        current_usd = result.cash_data.get('USD', 0) or 0
        result.cash_data['USD'] = current_usd + txn.amount_usd
        result.usd_total = result.usd_total + txn.amount_usd
        
        logger.debug(f"  SELL {txn.quantity} {txn.stock_code} @ ${txn.avg_price}")
    
    def _find_position(
        self, 
        positions: List[Dict], 
        stock_code: str
    ) -> Optional[Dict]:
        """
        Find position by stock code.
        
        For options, supports fuzzy matching since formats may differ:
        - Base portfolio: "CLI 250929 20.00 CALL" (in RawDescription)
        - TC file:        "2628 HK 06/29/26 C20"
        
        Uses existing parse_hk_option_description() and parse_us_option_description()
        """
        # First try exact match on StockCode
        for pos in positions:
            if pos['StockCode'] == stock_code:
                return pos
        
        # Try fuzzy matching for options using existing parsers
        # Parse TC file format
        parsed_tc = self._parse_option_with_existing_logic(stock_code)
        if parsed_tc:
            for pos in positions:
                # Try both StockCode and RawDescription for matching
                # RawDescription often contains the original broker format
                for code_field in ['StockCode', 'RawDescription']:
                    code_value = pos.get(code_field, '')
                    if not code_value:
                        continue
                    
                    parsed_pos = self._parse_option_with_existing_logic(code_value)
                    if parsed_pos and self._options_match(parsed_tc, parsed_pos):
                        logger.debug(
                            f"Fuzzy matched option: '{stock_code}' → '{pos['StockCode']}' "
                            f"(via {code_field}: '{code_value}')"
                        )
                        return pos
        
        return None
    
    def _parse_option_with_existing_logic(self, code: str) -> Optional[Dict]:
        """
        Parse option code using existing HK/US option parsers.
        
        Supports multiple option formats:
        - OCC format: "CLI260629C20000" (standardized format)
        - HKATS format: "CLI 250929 20.00 CALL"
        - Stock code + TC format: "2318 HK 09/29/25 C55"
        - Stock code + Base format: "2318 29SEP25 55 C"
        
        Reuses:
        - parse_hk_option_description() for HK HKATS format
        - parse_us_option_description() for US options
        
        Returns normalized dict with: expiry_date, strike, option_type, hkats_code/underlying
        """
        # Try OCC format FIRST (most likely after standardization)
        occ_parsed = self._parse_occ_format(code)
        if occ_parsed:
            return occ_parsed
        
        # Try HK stock code formats (before US parser to avoid false matches)
        # Format 1: TC file format "2318 HK 09/29/25 C55"
        # Format 2: Base portfolio format "2318 29SEP25 55 C"
        hk_stock_format = self._parse_hk_stock_code_option(code)
        if hk_stock_format:
            return hk_stock_format
        
        # Try HK option parser (HKATS format)
        hk_parsed = parse_hk_option_description(code)
        if hk_parsed:
            return hk_parsed
        
        # Try US option parser (last to avoid false matches)
        us_parsed = parse_us_option_description(code)
        if us_parsed:
            return us_parsed
        
        return None
    
    def _parse_occ_format(self, code: str) -> Optional[Dict]:
        """
        Parse OCC format option code: TICKER + 6digits + C/P + 5digits
        
        Examples:
        - "CLI260629C20000" → CLI, 2026-06-29, CALL, 20.0
        - "SBET260116P41000" → SBET, 2026-01-16, PUT, 41.0
        
        Returns same format as parse_hk_option_description()
        """
        import re
        from datetime import datetime
        
        # OCC format: TICKER(letters) + YYMMDD(6digits) + C/P + STRIKE*1000(5digits)
        match = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{5})$', code)
        if not match:
            return None
        
        ticker, date_str, opt_type, strike_str = match.groups()
        
        # Parse date: YYMMDD
        yy, mm, dd = date_str[:2], date_str[2:4], date_str[4:6]
        year = 2000 + int(yy)
        
        try:
            expiry_date = datetime(year, int(mm), int(dd))
        except ValueError:
            return None
        
        expiry_str = expiry_date.strftime('%Y-%m-%d')
        strike_float = int(strike_str) / 1000.0  # Convert back from *1000
        option_type_full = 'CALL' if opt_type == 'C' else 'PUT'
        
        logger.debug(f"Parsed OCC format: {code} → {ticker} {expiry_str} {strike_float} {option_type_full}")
        
        return {
            'hkats_code': ticker,  # Assume ticker is HKATS code for HK options
            'expiry_date': expiry_str,
            'strike': strike_float,
            'option_type': option_type_full
        }
    
    def _parse_hk_stock_code_option(self, code: str) -> Optional[Dict]:
        """
        Parse HK option in stock code formats and resolve HKATS code via Futu API.
        - TC file format: "2318 HK 09/29/25 C55"  -> Query Futu to get CLI
        - IB PDF format: "2318 29SEP25 55 C"      -> Query Futu to get CLI
        
        Uses Futu API to ensure accurate stock_code -> HKATS code mapping.
        
        Returns same format as parse_hk_option_description()
        """
        import re
        from datetime import datetime
        
        # Pattern 1: TC format - {stock_code} HK {MM}/{DD}/{YY} {C/P}{strike}
        match = re.match(r'(\d{4})\s+HK\s+(\d{2})/(\d{2})/(\d{2})\s+([CP])(\d+(?:\.\d+)?)', code)
        if match:
            stock_code, mm, dd, yy, opt_type, strike = match.groups()
            
            year = 2000 + int(yy)
            try:
                expiry_date = datetime(year, int(mm), int(dd))
            except ValueError:
                # Try DD/MM instead of MM/DD
                try:
                    expiry_date = datetime(year, int(dd), int(mm))
                except ValueError:
                    return None
            
            expiry_str = expiry_date.strftime('%Y-%m-%d')
            strike_float = float(strike)
            option_type_full = 'CALL' if opt_type == 'C' else 'PUT'
            
            # Query Futu API to get HKATS code (with cache)
            try:
                hkats_code = self.resolve_hk_numeric_to_hkats(stock_code)
                
                # Check if resolution failed (returns original numeric code)
                # Success: hkats_code is alphabetic (e.g., 'CLI')
                # Failure: hkats_code is numeric (e.g., '2318')
                if hkats_code.isdigit():
                    logger.debug(f"Cannot resolve HKATS code for {code} via Futu API (no option chain)")
                    return None
            except (ValueError, RuntimeError) as e:
                logger.debug(f"Cannot resolve HKATS code for {code}: {e}")
                return None
            
            logger.debug(f"Resolved via Futu: {code} -> {hkats_code} {expiry_str} {strike_float} {option_type_full}")
            
            return {
                'hkats_code': hkats_code,
                'expiry_date': expiry_str,
                'strike': strike_float,
                'option_type': option_type_full
            }
        
        # Pattern 2: IB PDF format - {stock_code} {DD}{MMM}{YY} {strike} {C/P}
        match = re.match(r'(\d{4})\s+(\d{2})([A-Z]{3})(\d{2})\s+(\d+(?:\.\d+)?)\s+([CP])', code)
        if match:
            stock_code, day, month_str, year, strike, opt_type = match.groups()
            
            # Month mapping
            month_map = {
                'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
            }
            
            month = month_map.get(month_str)
            if not month:
                return None
            
            year_int = int(year)
            full_year = 2000 + year_int if year_int < 50 else 1900 + year_int
            
            expiry_str = f"{full_year}-{month}-{day}"
            strike_float = float(strike)
            option_type_full = 'CALL' if opt_type == 'C' else 'PUT'
            
            # Query Futu API to get HKATS code (with cache)
            try:
                hkats_code = self.resolve_hk_numeric_to_hkats(stock_code)
                
                # Check if resolution failed (returns original numeric code)
                if hkats_code.isdigit():
                    logger.debug(f"Cannot resolve HKATS code for {code} via Futu API (no option chain)")
                    return None
            except (ValueError, RuntimeError) as e:
                logger.debug(f"Cannot resolve HKATS code for {code}: {e}")
                return None
            
            logger.debug(f"Resolved via Futu: {code} -> {hkats_code} {expiry_str} {strike_float} {option_type_full}")
            
            return {
                'hkats_code': hkats_code,
                'expiry_date': expiry_str,
                'strike': strike_float,
                'option_type': option_type_full
            }
        
        return None
    
    def _options_match(self, opt1: Dict, opt2: Dict) -> bool:
        """
        Check if two parsed option codes represent the same option.
        
        For HK options: compares hkats_code, expiry_date, strike, option_type
        For US options: compares underlying, expiry_date, strike, option_type
        """
        # Check underlying symbol (HK options use hkats_code, US options use underlying)
        hkats1 = opt1.get('hkats_code')
        hkats2 = opt2.get('hkats_code')
        underlying1 = opt1.get('underlying', '')
        underlying2 = opt2.get('underlying', '')
        
        # For HK options (both have hkats_code)
        if hkats1 and hkats2:
            if hkats1 != hkats2:
                return False
        # For US options (both have underlying)
        elif underlying1 and underlying2:
            # Extract symbol from underlying (remove 'US.' prefix if present)
            symbol1 = underlying1.replace('US.', '')
            symbol2 = underlying2.replace('US.', '')
            if symbol1 != symbol2:
                return False
        # Mixed or missing identifiers
        else:
            return False
        
        # Check expiry dates
        date1 = opt1.get('expiry_date')
        date2 = opt2.get('expiry_date')
        if not date1 or not date2 or date1 != date2:
            return False
        
        # Check strikes
        strike1 = opt1.get('strike')
        strike2 = opt2.get('strike')
        if strike1 is None or strike2 is None:
            return False
        if abs(strike1 - strike2) > 0.01:  # Allow small floating point differences
            return False
        
        # Check option types
        type1 = opt1.get('option_type', '')
        type2 = opt2.get('option_type', '')
        if type1 != type2:
            return False
        
        return True
    
    def _update_prices(
        self, 
        results: List[ProcessedResult], 
        target_date: str,
        exchange_rates: Dict
    ):
        """
        Update prices for all positions to target date.
        Uses same logic as broker_processor.
        
        Args:
            results: Portfolio results to update
            target_date: Target date for prices
            exchange_rates: Exchange rates for the target date
        """
        logger.info(f"Updating prices to {target_date}...")
        
        # Collect all unique symbols
        unique_symbols = {}
        for result in results:
            for i, position in enumerate(result.positions):
                stock_code = position['StockCode']
                if stock_code not in unique_symbols:
                    unique_symbols[stock_code] = []
                unique_symbols[stock_code].append((result, i))
        
        logger.info(f"Fetching prices for {len(unique_symbols)} unique symbols")
        
        # Fetch prices for each symbol (same logic as broker_processor)
        successful = 0
        for symbol in unique_symbols:
            try:
                # Get first position to extract raw_description
                first_result, first_idx = unique_symbols[symbol][0]
                first_position = first_result.positions[first_idx]
                raw_description = first_position.get('RawDescription', '')
                
                # get_stock_price now returns (price, currency) tuple
                price, api_currency = get_stock_price(symbol, target_date, None, raw_description)
                
                if price is not None and price > 0.0 and api_currency:
                    # Use API-provided currency (determined by API type: US vs HK)
                    price_currency = api_currency
                    price_source = 'Futu'
                    
                    # Update all positions with this symbol
                    for result, pos_idx in unique_symbols[symbol]:
                        position = result.positions[pos_idx]
                        position['FinalPrice'] = price
                        position['FinalPriceSource'] = price_source
                        position['OptimizedPriceCurrency'] = price_currency
                    
                    successful += 1
                else:
                    logger.warning(f"No valid price returned for {symbol}")
                    self.price_failures.append(symbol)
                    
            except Exception as e:
                logger.error(
                    f"Exception while fetching price for {symbol}: {type(e).__name__}: {e}"
                )
                self.price_failures.append(symbol)
        
        logger.info(
            f"Price update complete: {successful}/{len(unique_symbols)} successful"
        )
        
        if self.price_failures:
            logger.warning(
                f"Failed to fetch prices for {len(self.price_failures)} symbols"
            )
    
    def _generate_update_report(
        self,
        base_date: str,
        target_date: str,
        transactions: List[Transaction],
        results: List[ProcessedResult]
    ):
        """
        Generate update report showing what changed.
        
        Args:
            base_date: Base date
            target_date: Target date
            transactions: Applied transactions
            results: Updated results
        """
        logger.info("\n" + "=" * 60)
        logger.info("Trade Confirmation Update Report")
        logger.info("=" * 60)
        logger.info(f"Base Date: {base_date}")
        logger.info(f"Target Date: {target_date}")
        logger.info(f"Transactions Applied: {len(transactions)}")
        
        # Count by direction
        buy_count = sum(1 for t in transactions if t.direction == 'BUY')
        sell_count = sum(1 for t in transactions if t.direction == 'SELL')
        logger.info(f"  - BUY: {buy_count}")
        logger.info(f"  - SELL: {sell_count}")
        
        # Total cash and positions
        total_cash = sum(r.usd_total for r in results)
        total_positions = len([p for r in results for p in r.positions])
        logger.info(f"Updated Portfolio:")
        logger.info(f"  - Total Cash (USD): ${total_cash:,.2f}")
        logger.info(f"  - Total Positions: {total_positions}")
        logger.info(f"  - Brokers: {len(results)}")
        
        if self.price_failures:
            logger.warning(f"Price Fetch Failures: {len(self.price_failures)}")
            for symbol in self.price_failures:
                logger.warning(f"  - {symbol}")
        
        logger.info("=" * 60)


def auto_detect_latest_base_date() -> str:
    """
    Auto-detect the latest available base date from saved portfolios.
    
    Returns:
        Latest date string in YYYY-MM-DD format
    """
    persistence = DataPersistence()
    available_dates = persistence.get_available_dates()
    
    if not available_dates:
        raise ValueError(
            "No base portfolio found. Please run normal mode first to "
            "generate a base portfolio."
        )
    
    latest_date = available_dates[-1]  # List is sorted
    logger.info(f"Auto-detected latest base date: {latest_date}")
    return latest_date

