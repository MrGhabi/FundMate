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
import copy

from src.broker_processor import ProcessedResult
from src.price_fetcher import PriceFetcher, get_stock_price
from src.data_persistence import DataPersistence
from src.exchange_rate_handler import exchange_handler
from src.config import settings
from src.enums import PositionContext, OptionType
from src.position import Position
from src.option_parser import parse_option


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
        self._option_parser_configured = False
    
    def _setup_option_parser(self):
        """
        Configure global option parser to resolve HK numeric codes via Futu.
        
        HKNumericParser requires a resolve function dependency; inject it once.
        """
        if self._option_parser_configured:
            return
        
        try:
            from .option_parser import register_parser, HKNumericParser
        except ImportError:
            try:
                from option_parser import register_parser, HKNumericParser
            except ImportError:
                logger.warning("Could not import option_parser, HK numeric resolution unavailable")
                return
        
        hk_parser = HKNumericParser(resolve_func=self.resolve_hk_numeric_to_hkats)
        register_parser(hk_parser)
        logger.info("Configured HKNumericParser with Futu API resolution")
        self._option_parser_configured = True

    def standardize_option_format(self, stock_code: str) -> str:
        """
        Normalize option codes so base portfolio and TC share the same canonical format.
        Uses option parser results; non-options are returned unchanged.
        """
        if not stock_code:
            return stock_code

        try:
            parsed = parse_option(stock_code)
        except Exception:
            return stock_code

        if parsed.format_type == 'UNPARSEABLE':
            return stock_code

        if parsed.format_type == 'OTC':
            return stock_code

        cp = 'C' if parsed.option_type == OptionType.CALL else 'P'

        if parsed.format_type == 'US_OCC':
            ticker = parsed.underlying or stock_code
            expiry = parsed.expiry_date.strftime('%y%m%d')
            strike_int = int(round(parsed.strike * 1000))
            return f"{ticker}{expiry}{cp}{strike_int:05d}"

        if parsed.format_type == 'HK_HKATS':
            expiry = parsed.expiry_date.strftime('%y%m%d')
            strike_str = f"{parsed.strike:.2f}"
            full_cp = 'CALL' if parsed.option_type == OptionType.CALL else 'PUT'
            return f"{parsed.underlying} {expiry} {strike_str} {full_cp}"

        return stock_code
    
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

    
    def process_with_trade_confirmation(
        self,
        base_broker_folder: str,
        base_date: str,
        target_date: str,
        tc_folder: str = "data/archives/TradeConfirmation",
        base_results_override: Optional[List[ProcessedResult]] = None,
        base_exchange_rates_override: Optional[Dict] = None
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
        # Ensure option parser can resolve HK numeric codes before processing
        self._setup_option_parser()
        
        logger.info("=" * 80)
        logger.info("PHASE 1: Processing Base Portfolio")
        logger.info("=" * 80)
        
        # Reprocess base statements from broker folder
        from broker_processor import BrokerStatementProcessor
        
        if base_results_override is not None and base_exchange_rates_override is not None:
            base_results = copy.deepcopy(base_results_override)
            base_exchange_rates = dict(base_exchange_rates_override)
        else:
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
                
                stock_code = self._remove_leading_prefix(stock_code.strip())
                
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
    
    @staticmethod
    def _remove_leading_prefix(stock_code: str) -> str:
        """
        Some brokers prepend routing codes (e.g., "GS 2628 HK ...").
        Strip the first token if it is pure letters and followed by a numeric HK/US pattern.
        """
        if not stock_code:
            return stock_code
        tokens = stock_code.split()
        if len(tokens) < 4:
            return stock_code
        first, second, third = tokens[0], tokens[1], tokens[2]
        if first.isalpha() and len(first) <= 4 and second.isdigit() and len(second) == 4:
            if third.upper() in {'HK', 'C1', 'US'}:
                return ' '.join(tokens[1:])
        return stock_code
    
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
        """
        position = self._find_position(result.positions, txn.stock_code, result.broker_name)
        
        if position:
            current_holding = self._normalize_holding(position.holding)
            position.holding = current_holding + txn.quantity
        else:
            new_position = Position(
                stock_code=txn.stock_code,
                holding=txn.quantity,
                broker_price=txn.avg_price,
                price_currency=txn.currency,
                raw_description=txn.stock_code,
                broker=result.broker_name,
                context=PositionContext.TC
            )
            result.positions.append(new_position)
            logger.debug(
                f"  Created new position with multiplier={new_position.multiplier} "
                f"for {txn.stock_code}"
            )
        
        current_usd = result.cash_data.get('USD', 0) or 0
        result.cash_data['USD'] = current_usd - txn.amount_usd
        result.usd_total = result.usd_total - txn.amount_usd
        logger.debug(f"  BUY {txn.quantity} {txn.stock_code} @ ${txn.avg_price}")
    
    def _apply_sell(self, result: ProcessedResult, txn: Transaction):
        """
        Apply a SELL transaction: decrease position OR create short position, increase cash.
        """
        position = self._find_position(result.positions, txn.stock_code, result.broker_name)
        is_short_sale = txn.quantity < 0
        
        if is_short_sale:
            abs_quantity = abs(txn.quantity)
            
            if position:
                current_holding = self._normalize_holding(position.holding)
                position.holding = current_holding - abs_quantity
            else:
                new_position = Position(
                    stock_code=txn.stock_code,
                    holding=-abs_quantity,
                    broker_price=txn.avg_price,
                    price_currency=txn.currency,
                    raw_description=txn.stock_code,
                    broker=result.broker_name,
                    context=PositionContext.TC
                )
                result.positions.append(new_position)
                logger.debug(
                    f"  Created new short position with multiplier={new_position.multiplier} "
                    f"for {txn.stock_code}"
                )
            
            logger.debug(f"  SELL SHORT {abs_quantity} {txn.stock_code} @ ${txn.avg_price}")
        else:
            if not position:
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
                    f"  {[p.stock_code for p in result.positions]}\n"
                    f"\nNote: For short sales, quantity should be negative (e.g., -500)"
                )
            
            current_holding = self._normalize_holding(position.holding)
            new_holding = current_holding - txn.quantity
            if new_holding < 0:
                raise ValueError(
                    f"SELL quantity exceeds current holding!\n"
                    f"Broker: {result.broker_name}\n"
                    f"Stock: {txn.stock_code}\n"
                    f"Current holding: {current_holding}\n"
                    f"SELL quantity: {txn.quantity}\n"
                    f"Resulting holding: {new_holding} (NEGATIVE!)\n"
                    f"This is not a 'Sell Short' (quantity should be negative for shorts).\n"
                    f"Please check the transaction data or base date."
                )
            
            position.holding = new_holding
            if abs(new_holding) < 1e-9:
                result.positions.remove(position)
                logger.debug(f"  Position {txn.stock_code} fully closed")
        
        current_usd = result.cash_data.get('USD', 0) or 0
        result.cash_data['USD'] = current_usd + txn.amount_usd
        result.usd_total = result.usd_total + txn.amount_usd
        logger.debug(f"  SELL {txn.quantity} {txn.stock_code} @ ${txn.avg_price}")
    
    def _find_position(
        self,
        positions: List,
        stock_code: str,
        broker_name: str = "TEMP"
    ) -> Optional[Position]:
        """
        Find matching position for a TC stock code.

        Leverages Position.matches_option for fuzzy matching so that different
        option representations (HK numeric vs HKATS vs OCC) still pair up.
        """
        normalized_code = self.standardize_option_format(stock_code)
        target = Position(
            stock_code=normalized_code,
            holding=0,
            broker=broker_name,
            context=PositionContext.TC
        )

        for idx, pos in enumerate(positions):
            pos_obj = self._ensure_position_object(pos, broker_name)
            positions[idx] = pos_obj
            if pos_obj.stock_code == normalized_code:
                return pos_obj

        if target.option_format:
            for pos in positions:
                if pos.option_format and target.matches_option(pos):
                    logger.debug(
                        f"Fuzzy matched option: '{stock_code}' → '{pos.stock_code}' "
                        f"({target.underlying} {target.strike} {target.option_type})"
                    )
                    return pos

        for pos in positions:
            pos_obj = self._ensure_position_object(pos, broker_name)
            if self.standardize_option_format(pos_obj.stock_code) == normalized_code:
                return pos_obj

        return None
    
    @staticmethod
    def _normalize_holding(value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(',', ''))
            except ValueError:
                return 0.0
        return 0.0
    
    def _ensure_position_object(
        self,
        position,
        broker_name: str,
        context: PositionContext = PositionContext.BASE
    ) -> Position:
        """
        Ensure every entry in result.positions is a Position instance.
        """
        if isinstance(position, Position):
            return position
        
        pos_obj = Position(
            stock_code=position.get('StockCode', ''),
            holding=self._normalize_holding(position.get('Holding', 0)),
            broker_price=position.get('BrokerPrice'),
            price_currency=position.get('PriceCurrency'),
            raw_description=position.get('RawDescription'),
            multiplier=position.get('Multiplier'),
            broker=broker_name,
            context=context
        )
        pos_obj.final_price = position.get('FinalPrice')
        pos_obj.final_price_source = position.get('FinalPriceSource', '')
        optimized_currency = position.get('OptimizedPriceCurrency')
        if optimized_currency:
            pos_obj.optimized_price_currency = optimized_currency
        return pos_obj
    
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
                pos_obj = self._ensure_position_object(position, result.broker_name)
                result.positions[i] = pos_obj
                stock_code = pos_obj.stock_code
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
                raw_description = first_position.raw_description or ''
                
                # get_stock_price now returns (price, currency) tuple
                price, api_currency = get_stock_price(symbol, target_date, None, raw_description)
                
                if price is not None and price > 0.0 and api_currency:
                    # Use API-provided currency (determined by API type: US vs HK)
                    price_currency = api_currency
                    price_source = 'Futu'
                    
                    # Update all positions with this symbol
                    for result, pos_idx in unique_symbols[symbol]:
                        position = result.positions[pos_idx]
                        position.final_price = price
                        position.final_price_source = price_source
                        position.optimized_price_currency = price_currency
                    
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
