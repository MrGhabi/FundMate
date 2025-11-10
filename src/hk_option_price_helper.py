#!/usr/bin/env python3
"""
HK Option Price Helper - Futu API Integration
Provides price data for HK options using Futu API
"""

from typing import Optional, Tuple
from loguru import logger
import re
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from src.config import settings


def parse_hk_option_description(description: str) -> Optional[dict]:
    """
    Parse HK option description from broker statement
    
    Examples:
        "CLI 250929 19.00 CALL" -> HKATS: CLI, expiry: 2025-09-29, strike: 19.00, type: CALL
        "(CLI.HK 20250929 CALL 19.0)" -> same as above
    
    Returns:
        dict with: hkats_code, expiry_date, strike, option_type
    """
    if not description:
        return None
    
    try:
        # Pattern 1: "CLI 250929 19.00 CALL"
        pattern1 = r'([A-Z]{3})\s+(\d{6})\s+(\d+\.?\d*)\s+(CALL|PUT)'
        match = re.search(pattern1, description.upper())
        
        if match:
            hkats, date_str, strike, opt_type = match.groups()
            
            # Convert YYMMDD to YYYY-MM-DD
            year = int('20' + date_str[0:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            expiry_date = f"{year:04d}-{month:02d}-{day:02d}"
            
            return {
                'hkats_code': hkats,
                'expiry_date': expiry_date,
                'strike': float(strike),
                'option_type': opt_type
            }
        
        # Pattern 2: "(CLI.HK 20250929 CALL 19.0)"
        pattern2 = r'\(([A-Z]{3})\.HK\s+(\d{8})\s+(CALL|PUT)\s+(\d+\.?\d*)\)'
        match = re.search(pattern2, description.upper())
        
        if match:
            hkats, date_str, opt_type, strike = match.groups()
            
            # Convert YYYYMMDD to YYYY-MM-DD
            year = int(date_str[0:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            expiry_date = f"{year:04d}-{month:02d}-{day:02d}"
            
            return {
                'hkats_code': hkats,
                'expiry_date': expiry_date,
                'strike': float(strike),
                'option_type': opt_type
            }
            
    except Exception as e:
        logger.debug(f"Failed to parse HK option description '{description}': {e}")
    
    return None


def construct_hk_option_code(hkats_code: str, expiry_date: str, strike: float, option_type: str) -> str:
    """
    Construct Futu HK option code
    
    Format: HK.{HKATS}{YYMMDD}{C/P}{STRIKE*1000}
    Example: HK.CLI250929C19000
    
    Args:
        hkats_code: 3-letter HKATS code (e.g., CLI)
        expiry_date: YYYY-MM-DD format
        strike: Strike price
        option_type: CALL or PUT
    
    Returns:
        Futu option code
    """
    # Extract date components
    year, month, day = expiry_date.split('-')
    yy = year[2:]  # Last 2 digits
    
    # Option type letter
    opt_letter = 'C' if option_type == 'CALL' else 'P'
    
    # Strike price in integer format (multiply by 1000)
    strike_int = int(strike * 1000)
    
    # Construct code
    futu_code = f"HK.{hkats_code}{yy}{month}{day}{opt_letter}{strike_int:05d}"
    
    return futu_code


def get_hk_option_price_from_futu(stock_code: str, raw_description: str, date: str) -> Optional[float]:
    """
    Get HK option price from Futu API
    
    Process:
    1. Parse option details from description
    2. Construct Futu option code
    3. Query historical K-line for the specified date
    4. Extract close price from historical data
    
    Args:
        stock_code: Stock code from broker
        raw_description: Raw description from broker statement
        date: Query date (YYYY-MM-DD) - will fetch historical price for this date
    
    Returns:
        Price or None if failed
    """
    try:
        import futu as ft
        
        # Try to parse from raw_description first, then stock_code
        option_info = parse_hk_option_description(raw_description or stock_code)
        if not option_info:
            logger.debug(f"Cannot parse HK option: {stock_code} / {raw_description}")
            return None
        
        logger.debug(f"Parsed HK option: {option_info}")
        
        # Construct Futu option code
        futu_code = construct_hk_option_code(
            option_info['hkats_code'],
            option_info['expiry_date'],
            option_info['strike'],
            option_info['option_type']
        )
        
        logger.debug(f"Constructed Futu code: {futu_code}")
        
        quote_ctx = None
        try:
            quote_ctx = ft.OpenQuoteContext(host=settings.FUTU_HOST, port=settings.FUTU_PORT)
            
            # Try to get historical K-line for specified date
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
                return None
            
            ret = result[0]
            kline_data = result[1]
            
            if ret == ft.RET_OK and kline_data is not None and not kline_data.empty:
                # Got historical data - use it
                price = kline_data.iloc[0]['close']
                if price is None or price <= 0:
                    logger.debug(f"Invalid historical price for {futu_code}: {price}")
                    return None
                
                logger.success(f"Got HK option historical price: {futu_code} @ {date} -> ${price} HKD")
                return float(price)
            else:
                # No historical data - return None to use broker price
                # Never use current price as historical price - that's lying to the user
                logger.warning(f"No historical data for {futu_code} on {date}, will use broker price instead")
                return None
            
        finally:
            if quote_ctx:
                quote_ctx.close()
                
    except Exception as e:
        logger.debug(f"Error getting HK option price for {stock_code}: {e}")
        return None
