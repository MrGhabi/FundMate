#!/usr/bin/env python3
"""
US Option Price Helper - Futu API Integration
Provides price and multiplier data for US options using Futu API
"""

from typing import Optional, Tuple
from loguru import logger
import re
from datetime import datetime
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from src.config import settings


def parse_us_option_description(description: str) -> Optional[dict]:
    """
    Parse US option description from broker statement
    
    Examples:
        "AMZN US 06/18/26 C300" -> underlying: AMZN, expiry: 2026-06-18, strike: 300, type: CALL
        "COIN 04/18/25 C260" -> underlying: COIN, expiry: 2025-04-18, strike: 260, type: CALL
        "AMZN 18JUN26 300 C" -> underlying: AMZN, expiry: 2026-06-18, strike: 300, type: CALL (IB format)
        "TRON 20260116 PUT 15.0" -> underlying: TRON, expiry: 2026-01-16, strike: 15.0, type: PUT (Futu format)
    
    Returns:
        dict with: underlying, expiry_date, strike, option_type
    """
    if not description:
        return None
    
    try:
        upper_desc = description.upper()
        
        # Try Pattern 1: SYMBOL [US] MM/DD/YY [C/P]STRIKE
        pattern1 = r'([A-Z]+)\s+(?:US\s+)?(\d{2})/(\d{2})/(\d{2})\s+([CP])(\d+\.?\d*)'
        match = re.search(pattern1, upper_desc)
        
        if match:
            symbol, month, day, year, opt_type, strike = match.groups()
            
            # Convert YY to YYYY
            year_int = int(year)
            full_year = 2000 + year_int if year_int < 50 else 1900 + year_int
            
            # Format date
            expiry_date = f"{full_year}-{month}-{day}"
            
            return {
                'underlying': f'US.{symbol}',
                'expiry_date': expiry_date,
                'strike': float(strike),
                'option_type': 'CALL' if opt_type == 'C' else 'PUT'
            }
        
        # Try Pattern 2: IB format - SYMBOL DDMMMYY STRIKE C/P
        pattern2 = r'([A-Z]+)\s+(\d{2})([A-Z]{3})(\d{2})\s+(\d+\.?\d*)\s+([CP])'
        match = re.search(pattern2, upper_desc)
        
        if match:
            symbol, day, month_str, year, strike, opt_type = match.groups()
            
            # Month mapping
            month_map = {
                'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
            }
            
            month = month_map.get(month_str)
            if not month:
                logger.debug(f"Unknown month abbreviation: {month_str}")
                return None
            
            # Convert YY to YYYY
            year_int = int(year)
            full_year = 2000 + year_int if year_int < 50 else 1900 + year_int
            
            # Format date
            expiry_date = f"{full_year}-{month}-{day}"
            
            return {
                'underlying': f'US.{symbol}',
                'expiry_date': expiry_date,
                'strike': float(strike),
                'option_type': 'CALL' if opt_type == 'C' else 'PUT'
            }
        
        # Try Pattern 3: Futu format - SYMBOL YYYYMMDD PUT/CALL STRIKE
        pattern3 = r'([A-Z]+)\s+(\d{8})\s+(PUT|CALL)\s+(\d+\.?\d*)'
        match = re.search(pattern3, upper_desc)
        
        if match:
            symbol, date_str, opt_type, strike = match.groups()
            
            # Parse YYYYMMDD
            year = int(date_str[0:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            
            # Format date
            expiry_date = f"{year:04d}-{month:02d}-{day:02d}"
            
            return {
                'underlying': f'US.{symbol}',
                'expiry_date': expiry_date,
                'strike': float(strike),
                'option_type': opt_type
            }
            
    except Exception as e:
        logger.debug(f"Failed to parse US option description '{description}': {e}")
    
    return None


def get_us_option_price_from_futu(stock_code: str, raw_description: str, date: str) -> Tuple[Optional[float], Optional[int]]:
    """
    Get US option price and multiplier from Futu API
    
    Process:
    1. Parse option details from raw_description
    2. Construct Futu option code
    3. Query historical K-line for the specified date
    4. Extract close price from historical data
    
    Args:
        stock_code: Stock code from broker
        raw_description: Raw description from broker statement
        date: Query date (YYYY-MM-DD) - will fetch historical price for this date
    
    Returns:
        Tuple of (price, multiplier) or (None, None) if failed
    """
    try:
        import futu as ft
        
        # Parse option details
        option_info = parse_us_option_description(raw_description)
        if not option_info:
            logger.debug(f"Cannot parse US option: {raw_description}")
            return None, None
        
        logger.debug(f"Parsed US option: {option_info}")
        
        quote_ctx = None
        try:
            quote_ctx = ft.OpenQuoteContext(host=settings.FUTU_HOST, port=settings.FUTU_PORT)
            
            # Step 1: Construct Futu option code
            # Format: US.{SYMBOL}{YYMMDD}{C/P}{STRIKE*1000}
            symbol = option_info['underlying'].replace('US.', '')
            expiry_str = option_info['expiry_date'].replace('-', '')[2:]  # YYMMDD
            opt_letter = 'C' if option_info['option_type'] == 'CALL' else 'P'
            strike_code = f"{int(option_info['strike'] * 1000):05d}"
            
            futu_code = f"US.{symbol}{expiry_str}{opt_letter}{strike_code}"
            logger.debug(f"Constructed Futu option code: {futu_code}")
            
            # Step 2: Get historical K-line for specified date
            result = quote_ctx.request_history_kline(
                code=futu_code,
                start=date,
                end=date,
                ktype=ft.KLType.K_DAY,
                autype=ft.AuType.QFQ
            )
            
            # Handle 3-element tuple return (ret, data, page_req_key)
            if not isinstance(result, tuple) or len(result) < 2:
                logger.debug(f"Unexpected return format from request_history_kline")
                return None, None
            
            ret = result[0]
            kline_data = result[1]
            
            if ret != ft.RET_OK or kline_data.empty:
                logger.debug(f"No historical K-line data for {futu_code} on {date}")
                return None, None
            
            # Step 3: Extract close price
            price = kline_data.iloc[0]['close']
            if price is None or price <= 0:
                logger.debug(f"Invalid price for {futu_code}: {price}")
                return None, None
            
            # US options standard multiplier is 100
            multiplier = 100
            
            logger.success(f"Got US option historical price: {futu_code} @ {date} -> ${price}, multiplier: {multiplier}")
            return float(price), multiplier
            
        finally:
            if quote_ctx:
                quote_ctx.close()
                
    except Exception as e:
        logger.debug(f"Error getting US option price for {raw_description}: {e}")
        return None, None
