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
    
    def _match_archive_filename(self, filename: str, broker: str, date: str) -> bool:
        """
        检查归档文件名是否匹配券商和日期
        归档文件名格式: {BROKER}_{YYYY-MM-DD}_{ID}.ext
        """
        # 允许大小写不敏感的匹配
        pattern = rf"{re.escape(broker)}_({re.escape(date)})_.*"
        return re.match(pattern, filename, re.IGNORECASE) is not None
    
    def parse_ms_file(self, file_path: str) -> List[OptionPosition]:
        """
        Parse Morgan Stanley Excel file.
        Data structure: Row 10 = headers, Row 11+ = data
        Key columns: Und Description (col 5), Option Qty (col 10)
        """
        try:
            df = pd.read_excel(file_path, sheet_name='Equity-T1', header=None)
            
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
                quantity_str = str(row.iloc[11]) if not pd.isna(row.iloc[11]) else "0"
                quantity = int(float(quantity_str.replace(",", ""))) if quantity_str != "0" else 0
                strike = row.iloc[7] if not pd.isna(row.iloc[7]) else None
                expiry_date = str(row.iloc[6]) if not pd.isna(row.iloc[6]) else None
                option_type = str(row.iloc[10]) if not pd.isna(row.iloc[10]) else None  # Call/Put (col 10)
                buy_sell = str(row.iloc[8]) if not pd.isna(row.iloc[8]) else None      # B/S
                
                # Extract broker price data (MS format)
                broker_price = row.iloc[14] if not pd.isna(row.iloc[14]) else None  # Option Price (col 14)
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
            df = pd.read_excel(file_path, sheet_name=0, header=None)  # First sheet
            
            # GS data starts at row 8 (0-indexed row 6 is header)
            header_row = 6
            data_start_row = 8
            
            positions = []
            
            # Extract data rows until we hit empty rows
            for i in range(data_start_row, len(df)):
                row = df.iloc[i]
                
                # Stop if we hit empty description or account
                if pd.isna(row.iloc[0]) or pd.isna(row.iloc[4]):  # Account or Description
                    break
                
                # Extract key fields
                account = str(row.iloc[0]) if not pd.isna(row.iloc[0]) else ""
                description = str(row.iloc[4]) if not pd.isna(row.iloc[4]) else ""
                quantity = int(row.iloc[8]) if not pd.isna(row.iloc[8]) else 0
                strike = row.iloc[14] if not pd.isna(row.iloc[14]) else None
                expiry_date = str(row.iloc[13]) if not pd.isna(row.iloc[13]) else None
                option_type = str(row.iloc[6]) if not pd.isna(row.iloc[6]) else None  # Call/Put
                buy_sell = str(row.iloc[3]) if not pd.isna(row.iloc[3]) else None     # Buy/Sell
                underlyer = str(row.iloc[9]) if not pd.isna(row.iloc[9]) else None   # Underlyer Symbol
                
                # Extract broker price data (GS format)
                broker_price = row.iloc[22] if not pd.isna(row.iloc[22]) else None  # Price1 (col 22)
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
    
    def _convert_to_standard_format(self, positions: List[OptionPosition]) -> List[Dict[str, str]]:
        """
        Convert OptionPosition objects to standard position format.
        
        Args:
            positions: List of OptionPosition objects
            
        Returns:
            List of dicts in format: [{'StockCode': str, 'Holding': str}, ...]
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
                holding = str(-pos.quantity) if pos.quantity > 0 else str(pos.quantity)
            else:
                # Option buy should be positive
                holding = str(pos.quantity)
            
            standard_positions.append({
                'StockCode': stock_code,
                'Holding': holding,
                'RawDescription': pos.description,  # Preserve original description for option processing
                'BrokerPrice': pos.broker_price,    # Broker option price
                'PriceCurrency': pos.price_currency # Price currency
            })
        
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
    
    def parse_directory(self, directory_path: str, target_date: Optional[str] = None, archive_mode: bool = False) -> Dict[str, List[Dict[str, str]]]:
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
            Dict: {broker_name: [{'StockCode': str, 'Holding': str}, ...]}
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
            
            if archive_mode:
                # 归档模式：从文件名过滤
                if not target_date:
                    logger.error(f"Archive mode requires target_date parameter")
                    raise ValueError("Archive mode requires target_date parameter")
                
                # 查找文件名匹配 {券商}_{日期}_* 的Excel文件
                all_excel_files = list(broker_dir.glob("*.xls")) + list(broker_dir.glob("*.xlsx")) + \
                                 list(broker_dir.glob("*.XLS")) + list(broker_dir.glob("*.XLSX"))
                
                for excel_file in all_excel_files:
                    # 文件名格式: {BROKER}_{YYYY-MM-DD}_{ID}.xls
                    if self._match_archive_filename(excel_file.name, broker_name, target_date):
                        excel_files.append(excel_file)
                
                if not excel_files:
                    logger.warning(f"No archived Excel files found for {broker_name} on {target_date}")
                    logger.warning(f"Expected filename pattern: {broker_name}_{target_date}_*.xls[x]")
                    continue
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

            for file_path in excel_files:
                logger.info(f"Processing Excel file: {file_path}")
                
                if broker_name == "MS":
                    positions = self.parse_ms_file(str(file_path))
                elif broker_name == "GS":
                    positions = self.parse_gs_file(str(file_path))
                else:
                    logger.warning(f"Unknown Excel broker: {broker_name}, skipping")
                    continue
                
                # Convert to standard format
                standard_positions = self._convert_to_standard_format(positions)
                broker_positions.extend(standard_positions)
                logger.success(f"Extracted {len(positions)} positions from {file_path.name}")
            
            if broker_positions:
                results[broker_name] = broker_positions
        
        return results
    
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
            print(f"  {pos['StockCode']}: {pos['Holding']}")
        if len(positions) > 5:
            print(f"  ... and {len(positions) - 5} more")


if __name__ == "__main__":
    main()
