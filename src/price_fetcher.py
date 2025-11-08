#!/usr/bin/env python3
"""
Price Fetcher - Do one thing: get stock prices reliably

Linux philosophy: Simple, focused, composable
"""

import akshare as ak
import time
import re
from typing import Optional
from loguru import logger

try:
    from .config import settings
    from .exchange_rate_handler import exchange_handler
    from .utils import get_option_multiplier
    from .us_option_price_helper import get_us_option_price_from_futu
    from .hk_option_price_helper import get_hk_option_price_from_futu
except (ImportError, ValueError):
    from config import settings
    from exchange_rate_handler import exchange_handler
    from utils import get_option_multiplier
    from us_option_price_helper import get_us_option_price_from_futu
    from hk_option_price_helper import get_hk_option_price_from_futu


def normalize_symbol(raw_symbol: str) -> Optional[str]:
    """Clean broker symbol to tradeable format"""
    if not raw_symbol:
        return None
    
    symbol = raw_symbol.strip()
    
    # Extract from "Company (SYMBOL)" format
    if '(' in symbol and ')' in symbol:
        match = re.search(r'\(([^)]+)\)', symbol)
        if match:
            return match.group(1).strip()
    
    return symbol.upper() if symbol not in ['', 'N/A'] else None


def get_price_akshare(symbol: str, date: str) -> Optional[float]:
    """Get price via akshare"""
    try:
        date_str = date.replace('-', '')
        
        if symbol.isdigit():
            # HK stock
            df = ak.stock_hk_hist(symbol=symbol.zfill(5), period="daily",
                                start_date=date_str, end_date=date_str, adjust="qfq")
        else:
            # US stock - try with 105 prefix
            df = ak.stock_us_hist(symbol=f'105.{symbol}', period="daily",
                                start_date=date_str, end_date=date_str, adjust="qfq")
        
        return float(df.iloc[0]['收盘']) if not df.empty else None
    except:
        return None


def get_price_futu(symbol: str, date: str) -> Optional[float]:
    """Get price via futu API"""
    quote_ctx = None
    try:
        import futu as ft
        
        quote_ctx = ft.OpenQuoteContext(
            host=settings.FUTU_HOST, 
            port=settings.FUTU_PORT
        )
        
        # Format symbol for futu
        if symbol.isdigit():
            futu_symbol = f'HK.{symbol.zfill(5)}'
        else:
            futu_symbol = f'US.{symbol}'
        
        # Subscribe and get historical data
        ret, msg = quote_ctx.subscribe([futu_symbol], [ft.SubType.K_DAY])
        if ret != ft.RET_OK:
            return None
        
        time.sleep(1)
        
        # Get sufficient historical data (300 days covers about 10 months)
        ret, data = quote_ctx.get_cur_kline(futu_symbol, num=300, ktype=ft.KLType.K_DAY)
        
        if ret != ft.RET_OK or data.empty:
            return None
        
        # Try exact date match first (more reliable than date parsing)
        target_data = data[data['time_key'].astype(str).str.contains(date, na=False)]
        
        if not target_data.empty:
            return float(target_data.iloc[0]['close'])
        
        # If exact date not found, return None to fallback to broker price
        logger.debug(f"No exact date match for {symbol} on {date}, will use broker price")
        return None
        
    except Exception as e:
        logger.debug(f"Futu API error for {symbol}: {e}")
        return None
    finally:
        # Always close connection
        if quote_ctx:
            try:
                quote_ctx.close()
            except:
                pass


def get_stock_price(symbol: str, date: str, source: str = None, raw_description: str = None) -> tuple[Optional[float], Optional[str]]:
    """
    Get stock price for given symbol and date
    
    Args:
        symbol: Raw symbol from broker (e.g., "AAPL", "00700", "Apple Inc. (AAPL)")  
        date: Date string YYYY-MM-DD
        source: Override source ("akshare", "futu"), or None to use config
        raw_description: Optional raw description for better option parsing
    
    Returns:
        Tuple of (price, currency) where:
        - price: float or None
        - currency: 'USD', 'HKD', or None
        Currency is determined by API type (US vs HK)
    """
    # Option detection and processing - minimal implementation
    description = raw_description or symbol
    
    # Unified option detection (consistent with is_option_contract in utils.py)
    # Support full keywords (CALL/PUT/OPTION), space+letter (C/P), and letter+digits (P41, C300)
    upper_desc = description.upper()
    is_option = (
        any(keyword in upper_desc for keyword in ['OPTION', 'CALL', 'PUT']) or
        upper_desc.endswith(' C') or upper_desc.endswith(' P') or
        re.search(r'[\s][CP]\d+', upper_desc)  # Matches " P41", " C300", etc.
    )
    
    if is_option:
        # Try US option format first (support multiple formats)
        # Format 1: "AMZN US 06/18/26 C300"
        # Format 2: "AMZN 18JUN26 300 C" (IB format)
        is_us_option = (
            'US' in description.upper() or
            re.search(r'\d{2}/\d{2}/\d{2}', description) or  # MM/DD/YY format
            re.search(r'\d{2}[A-Z]{3}\d{2}', description)    # DDMMMYY format (IB)
        )
        
        if is_us_option:
            price, _ = get_us_option_price_from_futu(symbol, description, date)
            if price:
                return (price, 'USD')  # US option API returns USD
        
        # Try HK option format (e.g., "CLI 250929 19.00 CALL")
        # Check for HKATS code pattern: 3 letters + 6 digits
        if re.search(r'[A-Z]{3}\s+\d{6}', description):
            price = get_hk_option_price_from_futu(symbol, description, date)
            if price:
                return (price, 'HKD')  # HK option API returns HKD
        
        # Fallback to Morgan option format
        option_info = parse_morgan_option(symbol)
        if option_info:
            # Extract expiry date from option string if available
            expiry_date = None
            if 'EXP' in symbol:
                exp_match = re.search(r'EXP (\d{2}/\d{2}/\d{4})', symbol)
                if exp_match:
                    from datetime import datetime
                    try:
                        exp_date = datetime.strptime(exp_match.group(1), '%m/%d/%Y')
                        expiry_date = exp_date.strftime('%Y-%m-%d')
                    except:
                        pass
            
            option_code = find_closest_futu_option(option_info['underlying'], option_info['strike'], expiry_date)
            if option_code:
                price = get_option_price_futu(option_code, date)
                if price:
                    # Morgan OTC options are HK-based
                    return (price, 'HKD')
    
    clean_symbol = normalize_symbol(symbol)
    if not clean_symbol:
        return (None, None)
    
    # Simple: use configured source or override
    use_source = source or settings.PRICE_SOURCE
    
    # Determine currency based on symbol format
    # HK stocks: numeric codes (00700, 01810, etc.)
    # US stocks: letter codes (AAPL, TSLA, etc.)
    is_hk_stock = clean_symbol.isdigit()
    currency = 'HKD' if is_hk_stock else 'USD'
    
    if use_source == "futu":
        price = get_price_futu(clean_symbol, date)
        return (price, currency) if price else (None, None)
    elif use_source == "akshare":
        price = get_price_akshare(clean_symbol, date)
        return (price, currency) if price else (None, None)
    else:
        # Default to futu for unknown sources
        price = get_price_futu(clean_symbol, date)
        return (price, currency) if price else (None, None)


def calculate_portfolio_value(holdings, date: str, source: str = None, exchange_rates: dict = None, image_processor=None):
    """
    Calculate total portfolio value
    
    Args:
        holdings: List of {'symbol': str, 'shares': int} dicts
        date: Date string YYYY-MM-DD
        source: Override source, or None to use config defaults
        exchange_rates: Exchange rate data for currency conversion
    
    Returns:
        Dict with total value and per-stock breakdown
    """
    results = []
    total_value = 0.0
    
    for holding in holdings:
        # Support multiple field name formats for flexibility
        symbol = holding.get('symbol') or holding.get('StockCode')
        shares_raw = holding.get('shares') or holding.get('Holding') or holding.get('quantity', 0)
        
        # Ensure shares is numeric
        try:
            shares = int(float(str(shares_raw).replace(',', ''))) if shares_raw else 0
        except (ValueError, TypeError):
            shares = 0
        
        # Use raw description for option processing if available
        raw_description = holding.get('RawDescription')
        if raw_description and 'CALL' in raw_description.upper():
            symbol = raw_description  # Use original description for options
        
        if not symbol:
            continue
        
        # Priority: API price > broker price
        api_price, api_currency = get_stock_price(symbol, date, source, raw_description)  # Returns (price, currency)
        broker_price = holding.get('BrokerPrice')
        broker_currency = holding.get('PriceCurrency', 'USD')
        
        if api_price is not None and api_price > 0.0:
            price = api_price
            price_currency = api_currency or 'USD'
            price_source = "API"
        elif broker_price is not None:
            price = broker_price
            price_source = "Broker"
            
            # Strict currency validation - fail fast if invalid
            if not broker_currency or broker_currency not in ['USD', 'HKD', 'CNY']:
                raise RuntimeError(
                    f"Invalid or missing broker currency for {symbol}\n"
                    f"  Broker: {holding.get('Broker', 'Unknown')}\n"
                    f"  StockCode: {symbol}\n"
                    f"  RawDescription: {raw_description or 'N/A'}\n"
                    f"  BrokerCurrency: {broker_currency}\n"
                    f"  Expected: One of ['USD', 'HKD', 'CNY']\n"
                    f"  Action: Fix prompt to extract correct PriceCurrency field"
                )
            price_currency = broker_currency
        else:
            price = None
            price_currency = 'USD'
            price_source = "Failed"
        
        # Calculate position value (preserve sign for short/long positions)
        # Apply correct multiplier based on instrument type
        if price:
            broker_multiplier = holding.get('Multiplier')
            multiplier = get_option_multiplier(symbol, raw_description, broker_multiplier)
            value = price * shares * multiplier
            
            if multiplier > 1:
                logger.debug(f"Applied {multiplier}x option multiplier for {symbol}: {shares} × {price} × {multiplier} = {value}")
            else:
                logger.debug(f"Stock/OTC calculation for {symbol}: {shares} × {price} = {value}")
        else:
            value = 0.0
        
        # Use original symbol for display, not the raw description
        display_symbol = holding.get('symbol') or holding.get('StockCode')
        
        # Convert individual position value to USD for portfolio total
        if price_currency != 'USD' and value > 0:
            if image_processor:
                # Lazy loading: fetch rate only when needed
                rate = exchange_handler.get_rate_lazy(price_currency, 'USD', date)
                usd_value = value * rate  # Direct multiplication since rate is from_currency→USD
            elif exchange_rates:
                # Fallback to old method if exchange_rates provided
                rate = exchange_rates.get(price_currency, 1.0)
                usd_value = value / rate  # Division for USD-based rates
            else:
                logger.warning(f"No exchange rate source available for {price_currency}, using original value")
                usd_value = value
        else:
            usd_value = value
        
        # Log detailed price and calculation information
        if price is not None:
            if price_currency != 'USD' and exchange_rates and usd_value != value:
                logger.info(f"Stock: {display_symbol}, Shares: {shares:,}, Price: ${price} {price_currency} (Source: {price_source}), Value: ${value:,.2f} {price_currency} → ${usd_value:,.2f} USD")
            else:
                logger.info(f"Stock: {display_symbol}, Shares: {shares:,}, Price: ${price} {price_currency} (Source: {price_source}), Value: ${value:,.2f} {price_currency}")
        else:
            logger.info(f"Stock: {display_symbol}, Shares: {shares:,}, Price: N/A (Source: {price_source}), Value: $0.00")
        
        results.append({
            'symbol': display_symbol,  # Use original symbol for display
            'shares': shares, 
            'price': price,
            'price_currency': price_currency,  # Preserve currency info
            'value': value
        })
        
        total_value += usd_value
        time.sleep(0.2)  # Rate limit
    
    return {
        'total_value': total_value,
        'holdings': results,
        'num_holdings': len(results),
        'successful_prices': len([r for r in results if r['price'] is not None]),
        'date': date
    }


# Compatibility wrapper for existing code
class PriceFetcher:
    """Thin wrapper for legacy compatibility"""
    
    def calculate_position_values(self, positions, date: str, exchange_rates: dict = None, image_processor=None):
        """Legacy interface adapter"""
        # Preserve RawDescription when converting to holdings format
        holdings = []
        for p in positions:
            holding = {'symbol': p['StockCode'], 'shares': p['Holding']}
            if 'RawDescription' in p:
                holding['RawDescription'] = p['RawDescription']
            # Pass broker price and currency information
            if 'BrokerPrice' in p:
                holding['BrokerPrice'] = p['BrokerPrice']
            if 'PriceCurrency' in p:
                holding['PriceCurrency'] = p['PriceCurrency']
            if 'Multiplier' in p:
                holding['Multiplier'] = p['Multiplier']
            holdings.append(holding)
        
        result = calculate_portfolio_value(holdings, date, exchange_rates=exchange_rates, image_processor=image_processor)
        
        # Convert to legacy format
        valued_positions = []
        for h in result['holdings']:
            valued_positions.append({
                'StockCode': h['symbol'],
                'Holding': h['shares'],
                'Price': h['price'],
                'MarketValue': h['value']
            })
        
        successful = sum(1 for h in result['holdings'] if h['price'] is not None)
        failed = len(holdings) - successful
        
        return {
            'positions': valued_positions,
            'total_value_usd': result['total_value'],
            'successful_prices': successful,
            'failed_prices': failed
        }


# ========== Option Processing - Minimal Implementation ==========

def parse_morgan_option(option_str: str) -> Optional[dict]:
    """
    Parse Morgan statement option string - minimal implementation
    
    Args:
        option_str: "CALL OTC-1810 1.0@28.0439 EXP 08/26/2026 XIAOMI-W (EURO)"
    
    Returns:
        {'underlying': 'HK.01810', 'strike': 28.0439} or None
    """
    if not option_str or 'CALL' not in option_str.upper():
        return None
    
    try:
        # Extract underlying code from OTC-XXXX pattern
        otc_match = re.search(r'OTC-(\d+)', option_str)
        if not otc_match:
            return None
        
        otc_code = otc_match.group(1)
        
        # Map OTC codes to Futu symbols
        otc_to_futu = {
            '1810': 'HK.01810',   # XIAOMI-W
            '0388': 'HK.00388',   # HKEX
            '600519': 'SH.600519', # KWEICHOW MOUTAI (A-share, might not work in Futu)
            '600702': 'SH.600702', # SHEDE SPIRITS (A-share, might not work in Futu) 
            '601318': 'SH.601318'  # CN PING AN (A-share, might not work in Futu)
        }
        
        underlying = otc_to_futu.get(otc_code)
        if not underlying:
            return None
        
        # Extract strike price: @28.0439
        strike_match = re.search(r'@([\d.]+)', option_str)
        strike = float(strike_match.group(1)) if strike_match else None
        
        if strike is None:
            return None
            
        return {'underlying': underlying, 'strike': strike}
    except:
        return None


def find_closest_futu_option(underlying: str, target_strike: float, expiry_date: str = None) -> Optional[str]:
    """
    Find closest strike price option in Futu with expiry date matching
    
    Args:
        underlying: 'HK.01810'
        target_strike: 28.0439
        expiry_date: '2025-12-30' (optional, for better matching)
    
    Returns:
        Futu option code like 'HK.MIU250929C28000' or None
    """
    quote_ctx = None
    try:
        import futu as ft
        
        quote_ctx = ft.OpenQuoteContext(host=settings.FUTU_HOST, port=settings.FUTU_PORT)
        
        # Get option chain
        ret, data = quote_ctx.get_option_chain(underlying)
        if ret != ft.RET_OK or data.empty:
            return None
        
        # Filter CALL options
        calls = data[data['option_type'] == 'CALL']
        if calls.empty:
            return None
        
        # If expiry_date provided, try to filter by expiry first
        # Note: Futu option codes contain date info, we can extract it
        if expiry_date:
            # Extract year-month from expiry_date (e.g., "2025-12-30" -> "2512")
            try:
                from datetime import datetime
                exp_date = datetime.strptime(expiry_date, '%Y-%m-%d')
                target_ym = f"{exp_date.year % 100:02d}{exp_date.month:02d}"
                
                # Filter options that match the year-month pattern
                matching_expiry = calls[calls['code'].str.contains(target_ym, na=False)]
                
                if not matching_expiry.empty:
                    calls = matching_expiry
                else:
                    # If no matching expiry found, return None instead of wrong expiry
                    return None
            except:
                pass  # If date parsing fails, continue with all options
        
        # Find closest strike price
        calls = calls.copy()  # Avoid SettingWithCopyWarning
        calls['strike_diff'] = abs(calls['strike_price'] - target_strike)
        closest = calls.sort_values('strike_diff').iloc[0]
        
        return closest['code']
        
    except:
        return None
    finally:
        if quote_ctx:
            try:
                quote_ctx.close()
            except:
                pass


def get_option_price_futu(option_code: str, date: str) -> Optional[float]:
    """
    Get Futu option historical price - minimal implementation
    
    Args:
        option_code: 'HK.MIU250929C28000'  
        date: '2025-02-28'
    
    Returns:
        Option price or None
    """
    quote_ctx = None
    try:
        import futu as ft
        
        quote_ctx = ft.OpenQuoteContext(host=settings.FUTU_HOST, port=settings.FUTU_PORT)
        
        # Subscribe to option
        ret, msg = quote_ctx.subscribe([option_code], [ft.SubType.K_DAY])
        if ret != ft.RET_OK:
            return None
        
        time.sleep(1)
        
        # Get historical data
        ret, data = quote_ctx.get_cur_kline(option_code, num=300, ktype=ft.KLType.K_DAY)
        if ret != ft.RET_OK or data.empty:
            return None
        
        # Try exact date match first
        target_data = data[data['time_key'].astype(str).str.contains(date, na=False)]
        if not target_data.empty:
            return float(target_data.iloc[0]['close'])
        
        # Find closest date before target
        try:
            import pandas as pd
            data['date_only'] = pd.to_datetime(data['time_key']).dt.date
            target_date_obj = pd.to_datetime(date).date()
            
            before_target = data[data['date_only'] <= target_date_obj]
            if not before_target.empty:
                return float(before_target.iloc[0]['close'])
        except:
            pass
        
        return None
        
    except:
        return None
    finally:
        if quote_ctx:
            try:
                quote_ctx.close()
            except:
                pass
