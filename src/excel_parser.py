#!/usr/bin/env python3
"""
Excel position data parser for broker statements.
Extracts option position data from MS and GS Excel files.
Integrates with main FundMate processing pipeline.
"""

import re
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

from src.enums import PositionContext
from src.position import Position


@dataclass
class OptionPosition:
    """Option position data structure"""
    broker: str
    account: str
    description: str
    quantity: int
    strike: Optional[float] = None
    expiry_date: Optional[str] = None
    option_type: Optional[str] = None  # Call/Put
    buy_sell: Optional[str] = None     # Buy/Sell
    underlyer: Optional[str] = None
    broker_price: Optional[float] = None  # Broker option price
    price_currency: Optional[str] = None  # Price currency


class ExcelPositionParser:
    """
    Excel position parser for broker statements.
    Converts Excel option data to standard position format.
    Follows Linus principle: simple, direct, no special cases.
    """
    
    def __init__(self):
        pass

    @staticmethod
    def _load_excel_df(path: str, sheet_name: int = 0, header=None, nrows: Optional[int] = None) -> pd.DataFrame:
        """
        Robust loader for both .xls and .xlsx files without depending on pandas/xlrd version quirks.
        """
        suffix = Path(path).suffix.lower()
        # Try pandas fast path first (xlsx/xlsm via openpyxl; xls via xlrd if available)
        try:
            engine = "openpyxl" if suffix in {".xlsx", ".xlsm"} else "xlrd"
            return pd.read_excel(path, sheet_name=sheet_name, header=header, nrows=nrows, engine=engine)
        except Exception:
            pass
        # Fallback for old .xls via xlrd3
        try:
            import xlrd3 as xlrd
            # Patch handle_note to skip assertion failures on comments/notes
            def _handle_note(self, data, txos):
                return
            xlrd.sheet.Sheet.handle_note = _handle_note  # type: ignore
            book = xlrd.open_workbook(path)
            sh = book.sheet_by_index(sheet_name if isinstance(sheet_name, int) else 0)
            rows = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
            df = pd.DataFrame(rows)
            if nrows is not None:
                df = df.head(nrows)
            return df
        except Exception as exc:
            logger.error(f"Failed to load Excel {path}: {exc}")
            return pd.DataFrame()
    
    @staticmethod
    def _find_header_row(df: pd.DataFrame, required_cols: list[str]) -> Optional[int]:
        """Find header row by matching required column keywords (case-insensitive substring)."""
        lower_required = [c.lower() for c in required_cols]
        for idx, row in df.iterrows():
            cells = [str(v).strip().lower() for v in row.tolist()]
            if all(any(req in cell for cell in cells) for req in lower_required):
                return idx
        return None
    
    @staticmethod
    def _first_date_in_df(df: pd.DataFrame) -> Optional[str]:
        """Extract first date-like value from DataFrame."""
        from datetime import datetime
        for val in df.values.flatten():
            if isinstance(val, datetime):
                return val.strftime("%Y-%m-%d")
            if isinstance(val, str):
                # Try common formats
                m1 = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", val)
                if m1:
                    return f"{m1.group(1)}-{m1.group(2)}-{m1.group(3)}"
                m2 = re.search(r"([A-Za-z]{3,})\s+(\d{1,2}),?\s+(20\d{2})", val)
                if m2:
                    try:
                        dt = datetime.strptime(" ".join(m2.groups()), "%B %d %Y")
                        return dt.strftime("%Y-%m-%d")
                    except Exception:
                        try:
                            dt = datetime.strptime(" ".join(m2.groups()), "%b %d %Y")
                            return dt.strftime("%Y-%m-%d")
                        except Exception:
                            pass
        return None
    
    def _extract_archive_date(self, filename: str, broker: str) -> Optional[str]:
        """
        Extract date from archive filename: {BROKER}_{YYYY-MM-DD}_{ID}.ext
        """
        pattern = rf"{re.escape(broker)}_(\d{{4}}-\d{{2}}-\d{{2}})_.*"
        match = re.match(pattern, filename, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
    
    def parse_ms_file(self, file_path: str) -> List[OptionPosition]:
        """
        Parse Morgan Stanley Excel file.
        Data structure: Row 10 = headers, Row 11+ = data
        Key columns: Und Description (col 5), Option Qty (col 10)
        """
        try:
            df = self._load_excel_df(file_path, sheet_name='Equity-T1', header=None)
            
            # MS data starts at row 11 (0-indexed row 10 is header)
            header_row = 10
            data_start_row = 11
            
            positions = []
            
            # Extract data rows until we hit empty rows
            for i in range(data_start_row, len(df)):
                row = df.iloc[i]
                
                # Stop if we hit empty description
                if pd.isna(row.iloc[5]):  # Und Description column
                    break
                
                # Extract key fields
                account = str(row.iloc[1]) if not pd.isna(row.iloc[1]) else ""
                description = str(row.iloc[5]) if not pd.isna(row.iloc[5]) else ""
                # Option Qty is in column 11, not 10
                quantity_raw = row.iloc[11] if len(row) > 11 else None
                try:
                    quantity_str = str(quantity_raw) if quantity_raw not in (None, "") else "0"
                    quantity = int(float(quantity_str.replace(",", ""))) if quantity_str != "0" else 0
                except Exception:
                    quantity = 0
                strike = row.iloc[7] if not pd.isna(row.iloc[7]) else None
                expiry_date = str(row.iloc[6]) if not pd.isna(row.iloc[6]) else None
                option_type = str(row.iloc[10]) if not pd.isna(row.iloc[10]) else None  # Call/Put (col 10)
                buy_sell = str(row.iloc[8]) if not pd.isna(row.iloc[8]) else None      # B/S
                
                # Extract broker price data (MS format)
                try:
                    broker_price_raw = row.iloc[14] if len(row) > 14 else None
                    broker_price = float(str(broker_price_raw).replace(",", "")) if broker_price_raw not in (None, "") else None
                except Exception:
                    broker_price = None  # Option Price (col 14)
                price_currency = str(row.iloc[13]) if not pd.isna(row.iloc[13]) else None  # Position Currency (col 13)
                
                # Extract underlyer from description (simple regex-free approach)
                underlyer = self._extract_underlyer_from_ms_description(description)
                
                position = OptionPosition(
                    broker="MS",
                    account=account,
                    description=description,
                    quantity=quantity,
                    strike=float(str(strike).replace(",", "")) if strike else None,
                    expiry_date=expiry_date,
                    option_type="Call" if option_type == "C" else "Put" if option_type == "P" else option_type,
                    buy_sell="Buy" if buy_sell == "B" else "Sell" if buy_sell == "S" else buy_sell,
                    underlyer=underlyer,
                    broker_price=float(broker_price) if broker_price else None,
                    price_currency=price_currency
                )
                
                positions.append(position)
            
            return positions
            
        except Exception as e:
            logger.error(f"Error parsing MS file {file_path}: {e}")
            return []
    
    def parse_gs_file(self, file_path: str) -> List[OptionPosition]:
        """
        Parse Goldman Sachs Excel file.
        Data structure: Row 6 = headers, Row 8+ = data
        Key columns: Description (col 4), Quantity (col 8)
        """
        try:
            df = self._load_excel_df(file_path, sheet_name=0, header=None)  # First sheet
            
            # GS data starts at row 8 (0-indexed row 6 is header)
            header_row = 6
            data_start_row = 8
            
            positions = []
            def to_int(val) -> int:
                try:
                    return int(float(str(val).replace(",", "")))
                except Exception:
                    return 0
            def to_float(val):
                try:
                    return float(str(val).replace(",", ""))
                except Exception:
                    return None
            
            # Extract data rows until we hit empty rows
            for i in range(data_start_row, len(df)):
                row = df.iloc[i]
                
                # Stop if we hit empty description or account
                if pd.isna(row.iloc[0]) or pd.isna(row.iloc[4]):  # Account or Description
                    break
                
                # Extract key fields
                account = str(row.iloc[0]) if not pd.isna(row.iloc[0]) else ""
                description = str(row.iloc[4]) if not pd.isna(row.iloc[4]) else ""
                quantity = to_int(row.iloc[8]) if not pd.isna(row.iloc[8]) else 0
                strike = row.iloc[14] if not pd.isna(row.iloc[14]) else None
                expiry_date = str(row.iloc[13]) if not pd.isna(row.iloc[13]) else None
                option_type = str(row.iloc[6]) if not pd.isna(row.iloc[6]) else None  # Call/Put
                buy_sell = str(row.iloc[3]) if not pd.isna(row.iloc[3]) else None     # Buy/Sell
                underlyer = str(row.iloc[9]) if not pd.isna(row.iloc[9]) else None   # Underlyer Symbol
                
                # Extract broker price data (GS format)
                broker_price = to_float(row.iloc[22]) if not pd.isna(row.iloc[22]) else None  # Price1 (col 22)
                price_currency = str(row.iloc[5]) if not pd.isna(row.iloc[5]) else None  # Ccy (col 5)
                
                position = OptionPosition(
                    broker="GS",
                    account=account,
                    description=description,
                    quantity=quantity,
                    strike=float(strike) if strike else None,
                    expiry_date=expiry_date,
                    option_type=option_type,
                    buy_sell=buy_sell,
                    underlyer=underlyer,
                    broker_price=float(broker_price) if broker_price else None,
                    price_currency=price_currency
                )
                
                positions.append(position)
            
            return positions
            
        except Exception as e:
            logger.error(f"Error parsing GS file {file_path}: {e}")
            return []
    
    def _extract_underlyer_from_ms_description(self, description: str) -> str:
        """
        Extract underlyer symbol from MS description.
        Example: "CALL OTC-1810 1.0@60.0 EXP 08/26/2026 XIAOMI-W (EURO)" -> "1810"
        Simple string parsing, no regex complexity.
        """
        if not description:
            return ""
        
        try:
            # Look for pattern "OTC-XXXX" where XXXX is the symbol
            if "OTC-" in description:
                start = description.find("OTC-") + 4
                end = description.find(" ", start)
                if end == -1:
                    end = len(description)
                return description[start:end]
        except:
            pass
        
        return ""
    
    def _convert_to_standard_format(self, positions: List[OptionPosition], broker_name: str = "EXCEL") -> List[Position]:
        """
        Convert OptionPosition objects to Position objects (new architecture)
        
        Args:
            positions: List of OptionPosition objects
            broker_name: Broker name for Position object
            
        Returns:
            List of Position objects
        """
        standard_positions = []
        
        for pos in positions:
            # For options, use the full description as StockCode
            # Format: "TSLA 18JUN26 800 C" style
            if pos.underlyer and pos.expiry_date and pos.strike and pos.option_type:
                # Try to construct standardized option symbol
                try:
                    stock_code = self._format_option_symbol(
                        pos.underlyer, pos.expiry_date, pos.strike, pos.option_type
                    )
                except:
                    # Fallback to description
                    stock_code = pos.description
            else:
                # Use description as-is
                stock_code = pos.description
            
            # Convert quantity to holding - preserve sign for sell positions  
            if pos.buy_sell == "Sell":
                # Option sell should be negative
                holding = -pos.quantity if pos.quantity > 0 else pos.quantity
            else:
                # Option buy should be positive
                holding = pos.quantity
            
            # Create Position object (will auto-parse option if detected)
            position_obj = Position(
                stock_code=stock_code,
                holding=holding,
                broker_price=pos.broker_price,
                price_currency=pos.price_currency,
                raw_description=pos.description,
                broker=broker_name,
                context=PositionContext.BASE
            )
            standard_positions.append(position_obj)
        
        return standard_positions
    
    def _format_option_symbol(self, underlyer: str, expiry_date: str, 
                             strike: float, option_type: str) -> str:
        """
        Format option into standardized symbol.
        Example: TSLA 18JUN26 800 C
        """
        try:
            # Parse expiry date
            import re
            from datetime import datetime
            
            # Handle different date formats
            if re.match(r'\d{4}-\d{2}-\d{2}', expiry_date):
                date_obj = datetime.strptime(expiry_date, '%Y-%m-%d')
            elif re.match(r'\d{2}/\d{2}/\d{4}', expiry_date):
                date_obj = datetime.strptime(expiry_date, '%m/%d/%Y')
            else:
                # Fallback to original
                return f"{underlyer} OPTION"
            
            # Format as DDMMMnn
            day = date_obj.strftime('%d')
            month = date_obj.strftime('%b').upper()
            year = date_obj.strftime('%y')
            
            # Format option type
            opt_type = 'C' if option_type.upper().startswith('C') else 'P'
            
            # Construct symbol
            return f"{underlyer} {day}{month}{year} {int(strike)} {opt_type}"
        
        except Exception as e:
            logger.warning(f"Failed to format option symbol: {e}")
            return f"{underlyer} OPTION"
    
    def parse_directory(self, directory_path: str, target_date: Optional[str] = None, archive_mode: bool = False) -> Dict[str, List[Position]]:
        """
        Parse all Excel files in directory structure.
        
        Args:
            directory_path: Path to directory containing Excel files
            target_date: Target date in YYYY-MM-DD format
            archive_mode: If True, use archive filename filtering; if False, use directory structure
        
        Expected structure:
            - Archive mode: directory/BROKER/{BROKER}_{YYYY-MM-DD}_*.xls
            - Statement mode: directory/BROKER/[DATE/]<files>.xls
        
        Returns:
            Dict: {broker_name: [Position objects]}
        """
        results = {}
        directory = Path(directory_path)
        
        if not directory.exists():
            logger.warning(f"Excel directory does not exist: {directory_path}")
            return {}
        
        logger.info(f"Scanning Excel directory: {directory_path}")
        
        # Look for broker subdirectories (support nested date folders)
        for broker_dir in directory.iterdir():
            if not broker_dir.is_dir():
                continue
            
            broker_name = broker_dir.name.upper()

            if broker_name.lower() == 'temp':
                logger.debug("Skipping temporary upload directory")
                continue
            logger.info(f"Found Excel broker directory: {broker_name}")
            
            broker_positions = []
            excel_files = []
            broker_statement_date: Optional[str] = None
            
            if archive_mode:
                # 归档模式：从文件名过滤
                if not target_date:
                    logger.error(f"Archive mode requires target_date parameter")
                    raise ValueError("Archive mode requires target_date parameter")
                
                # 查找最接近 target_date 的 Excel 文件
                all_excel_files = list(broker_dir.glob("*.xls")) + list(broker_dir.glob("*.xlsx")) + \
                                 list(broker_dir.glob("*.XLS")) + list(broker_dir.glob("*.XLSX"))
                dated_files = []
                for excel_file in all_excel_files:
                    matched_date = self._extract_archive_date(excel_file.name, broker_name)
                    if matched_date and matched_date <= target_date:
                        dated_files.append((matched_date, excel_file))
                
                if not dated_files:
                    logger.warning(f"No archived Excel files found for {broker_name} on or before {target_date}")
                    logger.warning(f"Expected filename pattern: {broker_name}_YYYY-MM-DD_*.xls[x]")
                    continue
                
                matched_date, excel_file = max(dated_files, key=lambda x: x[0])
                if matched_date != target_date:
                    logger.info(f"{broker_name}: no {target_date} Excel found; using nearest {matched_date}")
                excel_files.append(excel_file)
                broker_statement_date = matched_date
            else:
                # Statement模式：原有逻辑
                # Determine search paths (prefer date-specific folder if provided)
                search_paths = []
                if target_date:
                    date_dir = broker_dir / target_date
                    if date_dir.exists():
                        search_paths.append(date_dir)

                if not search_paths:
                    search_paths.append(broker_dir)

                # Process Excel files in broker directory (including nested folders)
                excel_files = [
                    file_path
                    for path in search_paths
                    for file_path in path.rglob("*")
                    if file_path.is_file() and file_path.suffix.lower() in ['.xls', '.xlsx']
                ]

                if not excel_files:
                    logger.info(f"No Excel files found for {broker_name}")
                    continue
                broker_statement_date = target_date

            for file_path in excel_files:
                logger.info(f"Processing Excel file: {file_path}")
                
                if broker_name == "MS":
                    positions = self.parse_ms_file(str(file_path))
                elif broker_name == "GS":
                    positions = self.parse_gs_file(str(file_path))
                elif broker_name == "GSPB":
                    gspb_data = self.parse_gspb_file(str(file_path))
                    if gspb_data:
                        broker_positions.extend(gspb_data["positions"])
                        broker_statement_date = broker_statement_date or gspb_data.get("statement_date")
                        # Stash cash/account for final merge
                        cash_data = gspb_data.get("cash_data")
                        account_id = gspb_data.get("account_id")
                        results[broker_name] = {
                            "positions": broker_positions,
                            "cash_data": cash_data,
                            "account_id": account_id,
                            "statement_date": broker_statement_date or target_date
                        }
                    continue
                else:
                    logger.warning(f"Unknown Excel broker: {broker_name}, skipping")
                    continue
                
                # Convert to standard format (now returns Position objects)
                standard_positions = self._convert_to_standard_format(positions, broker_name=broker_name)
                broker_positions.extend(standard_positions)
                logger.success(f"Extracted {len(positions)} positions from {file_path.name}")
            
            if broker_positions and broker_name != "GSPB":
                results[broker_name] = {
                    "positions": broker_positions,
                    "statement_date": broker_statement_date or target_date
                }
        
        return results
    
    def parse_gspb_file(self, file_path: str) -> Optional[Dict]:
        """
        Parse GSPB Excel for cash and positions from Custody sheets.
        Returns dict with positions (List[Position]), cash_data, account_id, statement_date.
        """
        positions: List[Position] = []
        cash_data: Optional[Dict[str, float]] = None
        account_id: Optional[str] = None
        statement_date: Optional[str] = None

        def _load_sheets(path: str) -> Dict[str, pd.DataFrame]:
            # Prefer robust xlrd3 fallback for old .xls; pandas can choke on xlrd version requirements
            try:
                import xlrd3 as xlrd
                # Patch handle_note to skip assertion failures on comments/notes
                def _handle_note(self, data, txos):
                    return
                xlrd.sheet.Sheet.handle_note = _handle_note  # type: ignore
                book = xlrd.open_workbook(path)
                sheets_dict: Dict[str, pd.DataFrame] = {}
                for name in book.sheet_names():
                    sh = book.sheet_by_name(name)
                    rows = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
                    sheets_dict[name] = pd.DataFrame(rows)
                return sheets_dict
            except Exception:
                pass
            # Fallback to pandas if xlrd3 fails (e.g., xlsx)
            try:
                return pd.read_excel(path, sheet_name=None, header=None)
            except Exception as exc:
                logger.error(f"GSPB: failed to read Excel {path} with fallbacks: {exc}")
                return {}

        sheets = _load_sheets(file_path)
        if not sheets:
            return None

        def parse_positions(df: pd.DataFrame):
            nonlocal account_id, statement_date, positions
            header_idx = None
            for idx, row in df.iterrows():
                cells = [str(v).strip().lower() for v in row.tolist()]
                if "description" in cells and any("trade date quantity" in c for c in cells):
                    header_idx = idx
                    break
            if header_idx is None:
                return
            statement_date_local = self._first_date_in_df(df)
            if statement_date_local:
                statement_date = statement_date or statement_date_local
            header = [str(c).strip() for c in df.iloc[header_idx].tolist()]
            data = df.iloc[header_idx + 1:].copy()

            def find_col(keyword: str) -> Optional[str]:
                for col in header:
                    if keyword.lower() in col.lower():
                        return col
                return None

            col_desc = find_col("Description")
            col_symbol = find_col("Symbol") or find_col("Cusip") or find_col("Sedol")
            col_qty = find_col("Trade Date Quantity") or find_col("Quantity")
            col_price = find_col("Market Price")
            col_value = find_col("Market Value")
            col_currency = find_col("Base Curr")
            col_account = find_col("Advisor") or find_col("Account")

            for _, row in data.iterrows():
                row_dict = {header[i]: row.iloc[i] if i < len(row) else None for i in range(len(header))}
                desc = str(row_dict.get(col_desc, "")).strip() if col_desc else ""
                symbol = str(row_dict.get(col_symbol, "")).strip() if col_symbol else ""
                if not desc and not symbol:
                    continue
                try:
                    qty = float(str(row_dict.get(col_qty, "0")).replace(",", "")) if col_qty else 0.0
                except Exception:
                    qty = 0.0
                try:
                    price = float(str(row_dict.get(col_price, "0")).replace(",", "")) if col_price else None
                except Exception:
                    price = None
                try:
                    market_value = float(str(row_dict.get(col_value, "0")).replace(",", "")) if col_value else None
                except Exception:
                    market_value = None

                currency = str(row_dict.get(col_currency, "")).strip() if col_currency else None
                account_val = str(row_dict.get(col_account, "")).strip() if col_account else None
                if account_val:
                    account_id = account_id or account_val

                multiplier = 1.0
                if price and qty:
                    try:
                        calc = market_value / (qty * price) if market_value else None
                        if calc and calc > 0:
                            multiplier = calc
                    except Exception:
                        pass

                pos = Position(
                    stock_code=symbol or desc,
                    holding=qty,
                    broker_price=price,
                    price_currency=currency or "USD",
                    raw_description=desc,
                    broker="GSPB",
                    multiplier=multiplier,
                    context=PositionContext.BASE
                )
                # Pre-fill final price/source/currency
                pos.final_price = price
                pos.final_price_source = "Broker"
                pos.optimized_price_currency = currency or "USD"
                # Store market value if available for later use
                if market_value is not None:
                    pos.position_value_usd = market_value  # type: ignore
                positions.append(pos)

        def parse_cash(df: pd.DataFrame):
            nonlocal cash_data, account_id, statement_date
            header_idx = None
            for idx, row in df.iterrows():
                cells = [str(v).strip().lower() for v in row.tolist()]
                if "account number" in cells and any("settle date" in c for c in cells):
                    header_idx = idx
                    break
            if header_idx is None:
                return
            statement_date_local = self._first_date_in_df(df)
            if statement_date_local:
                statement_date = statement_date or statement_date_local
            header = [str(c).strip() for c in df.iloc[header_idx].tolist()]
            data = df.iloc[header_idx + 1:].copy()

            def find_col(keyword: str) -> Optional[str]:
                for col in header:
                    if keyword.lower() in col.lower():
                        return col
                return None

            col_acc = find_col("Account Number")
            col_curr = find_col("Base Curr")
            col_amount = find_col("Settle Date + 2 Qty") or find_col("Settle Date Qty")

            if col_amount is None:
                return

            for _, row in data.iterrows():
                row_dict = {header[i]: row.iloc[i] if i < len(row) else None for i in range(len(header))}
                try:
                    amt = float(str(row_dict.get(col_amount, "0")).replace(",", ""))
                except Exception:
                    continue
                if amt == 0:
                    continue
                currency = str(row_dict.get(col_curr, "")).strip() if col_curr else "USD"
                acct = str(row_dict.get(col_acc, "")).strip() if col_acc else None
                if acct:
                    account_id = account_id or acct
                cash_data = {
                    currency: amt,
                    "Total": amt,
                    "Total_type": currency
                }
                break

        for df in sheets.values():
            parse_positions(df)
            parse_cash(df)

        if not positions and not cash_data:
            logger.warning(f"GSPB: no positions/cash parsed from {file_path}")
            return None

        return {
            "positions": positions,
            "cash_data": cash_data or {"Total": 0.0, "Total_type": "USD"},
            "account_id": account_id or "EXCEL",
            "statement_date": statement_date
        }
    
    def print_summary(self, positions: List[OptionPosition]) -> None:
        """Print summary of extracted positions"""
        if not positions:
            print("No positions found.")
            return
        
        print(f"\n=== Position Summary ===")
        print(f"Total positions: {len(positions)}")
        
        # Group by broker
        by_broker = {}
        for pos in positions:
            if pos.broker not in by_broker:
                by_broker[pos.broker] = []
            by_broker[pos.broker].append(pos)
        
        for broker, broker_positions in by_broker.items():
            print(f"\n{broker} Broker ({len(broker_positions)} positions):")
            for pos in broker_positions:
                print(f"  {pos.description}")
                print(f"    Quantity: {pos.quantity}")
                print(f"    Strike: {pos.strike}")
                print(f"    Expiry: {pos.expiry_date}")
                print(f"    Type: {pos.option_type} ({pos.buy_sell})")
                print(f"    Underlyer: {pos.underlyer}")
                print()


def main():
    """Main entry point for standalone testing"""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python excel_parser.py <directory_path>")
        print("Example: python excel_parser.py data/20250731_Statement")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    
    parser = ExcelPositionParser()
    results = parser.parse_directory(directory_path)
    
    print(f"\n=== Excel Position Summary ===")
    for broker_name, positions in results.items():
        print(f"\n{broker_name}: {len(positions)} positions")
        for pos in positions[:5]:  # Show first 5
            if hasattr(pos, 'stock_code'):
                print(f"  {pos.stock_code}: {pos.holding}")
            else:
                print(f"  {pos.get('StockCode')}: {pos.get('Holding')}")
        if len(positions) > 5:
            print(f"  ... and {len(positions) - 5} more")


if __name__ == "__main__":
    main()
