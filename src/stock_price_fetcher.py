#!/usr/bin/env python3
"""
Unified price fetcher for broker position valuation.
Handles both stocks and options in one place.
Integrates with existing broker processing system.
"""
import akshare as ak
import time
import re
from typing import Dict, List, Optional, Tuple
from loguru import logger
from datetime import datetime


class OptionContract:
    """Simple option contract data structure"""
    
    def __init__(self, symbol: str, expiry: str, strike: float, option_type: str, underlying: str):
        self.symbol = symbol           # Original symbol from broker
        self.expiry = expiry          # Expiry date string
        self.strike = strike          # Strike price
        self.option_type = option_type # 'C' or 'P'
        self.underlying = underlying   # Underlying asset
    
    def __repr__(self):
        return f"Option({self.underlying} {self.expiry} {self.strike} {self.option_type})"


class StockPriceFetcher:
    """
    Unified price fetcher following Linus principle:
    - One class, one responsibility  
    - Handle both stocks and options
    - Auto-detect stock markets (HK/US) and option types
    - Intelligent symbol normalization for different broker formats
    - Minimal error handling, maximum reliability
    """
    
    def __init__(self):
        # US stock prefix mapping for akshare
        self.us_prefix_map = {
            'AAPL': '105.AAPL', 'MSFT': '105.MSFT', 'GOOGL': '105.GOOGL',
            'HOOD': '105.HOOD', 'DUOL': '105.DUOL', 'COIN': '105.COIN',
            'BEKE': '106.BEKE', 'PDD': '105.PDD', 'CSIQ': '105.CSIQ',
            'BTCS': '105.BTCS', 'TSLA': '105.TSLA', 'AMZN': '105.AMZN',
            'NVDA': '105.NVDA', 'META': '105.META', 'NFLX': '105.NFLX'
        }
        
        # Option processing components
        self.option_cache = None
        self.cache_timestamp = None
        self.month_map = {
            'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
            'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08', 
            'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
        }
    
    def normalize_stock_symbol(self, raw_symbol: str) -> Optional[str]:
        """
        Normalize different broker symbol formats to standard stock codes.
        
        Examples:
            "TSLA 18JUN26 800 C" -> None (option, skip)
            "Duolingo, Inc. (DUOL)" -> "DUOL"
            "00700" -> "00700"
            "AAPL" -> "AAPL"
            
        Args:
            raw_symbol: Raw symbol from broker statement
            
        Returns:
            str: Normalized stock symbol, or None if not a stock
        """
        if not raw_symbol or not isinstance(raw_symbol, str):
            return None
            
        symbol = raw_symbol.strip()
        
        # Skip empty symbols
        if not symbol:
            return None
        
        # Pattern 1: Options (contains dates and strike prices)
        # Examples: "TSLA 18JUN26 800 C", "2318 29SEP25 55 C"
        if any(pattern in symbol.upper() for pattern in [
            'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
            'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'
        ]):
            if ' C' in symbol or ' P' in symbol:  # Call or Put
                logger.info(f"Identified option contract: {symbol}")
                return "OPTION"  # Special marker for options
        
        # Pattern 2: Company names with symbol in parentheses
        # Examples: "Duolingo, Inc. (DUOL)", "Apple Inc. (AAPL)"
        if '(' in symbol and ')' in symbol:
            import re
            match = re.search(r'\(([^)]+)\)', symbol)
            if match:
                extracted = match.group(1).strip()
                logger.info(f"Extracted symbol from company name: {symbol} -> {extracted}")
                return extracted
        
        # Pattern 3: Already clean symbols (with potential suffixes)
        # Examples: "AAPL", "00700", "TSLA", "AAPL.US", "BRK.B"
        if symbol.replace('.', '').replace('-', '').isalnum():
            # Remove common suffixes that aren't part of the symbol
            clean_symbol = symbol.split()[0]  # Take first word only
            
            # Handle common suffixes like .US, .B, .HK
            if '.' in clean_symbol:
                parts = clean_symbol.split('.')
                if len(parts) == 2:
                    base_symbol, suffix = parts
                    # Common exchange suffixes
                    if suffix.upper() in ['US', 'HK', 'TO', 'L']:
                        logger.debug(f"Removed exchange suffix: {clean_symbol} -> {base_symbol}")
                        return base_symbol
                    # Share class suffixes (but keep them as valid symbols)
                    elif suffix.upper() in ['A', 'B', 'C'] and len(suffix) == 1:
                        logger.debug(f"Keeping share class: {clean_symbol}")
                        return clean_symbol
            
            # Skip if it looks like an option (has numbers mixed with letters in complex ways)
            if len(clean_symbol) > 10:  # Very long symbols are probably not clean stock codes
                return None
                
            return clean_symbol
        
        # Pattern 4: Unknown format
        logger.warning(f"Unknown symbol format, skipping: {symbol}")
        return None
    
    def get_single_price(self, symbol: str, date: str, max_retries: int = 3) -> Optional[float]:
        """
        Get price for stock or option symbol with retry mechanism.
        
        Args:
            symbol: Raw symbol from broker (will be normalized)
            date: Date string like '2024-02-28' (unused for options)
            max_retries: Maximum number of retry attempts
            
        Returns:
            float: Price, or None if failed
        """
        # Step 1: Normalize the symbol
        normalized_symbol = self.normalize_stock_symbol(symbol)
        if normalized_symbol is None:
            return None  # Skip unrecognized symbols
        
        # Step 2: Handle options separately
        if normalized_symbol == "OPTION":
            logger.debug(f"Processing option: {symbol}")
            try:
                price = self.get_option_price(symbol)
                if price is None:
                    logger.info(f"Option price not available (likely overseas): {symbol}")
                return price
            except Exception as e:
                logger.warning(f"Option price fetch failed for {symbol}: {e}")
                return None
        
        # Step 3: Handle stocks
        logger.debug(f"Processing stock: {symbol} -> {normalized_symbol}")
        for attempt in range(max_retries):
            try:
                # Add delay between retries (except first attempt)
                if attempt > 0:
                    delay = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                    logger.info(f"Retrying {symbol} after {delay}s delay...")
                    time.sleep(delay)
                
                date_str = date.replace('-', '')  # Convert to YYYYMMDD
                
                if normalized_symbol.isdigit():
                    # HK stock: pad to 5 digits
                    ak_symbol = normalized_symbol.zfill(5)
                    df = ak.stock_hk_hist(
                        symbol=ak_symbol, 
                        period="daily",
                        start_date=date_str, 
                        end_date=date_str, 
                        adjust="qfq"
                    )
                else:
                    # US stock: add prefix
                    ak_symbol = self.us_prefix_map.get(
                        normalized_symbol.upper(), 
                        f'105.{normalized_symbol.upper()}'
                    )
                    df = ak.stock_us_hist(
                        symbol=ak_symbol,
                        period="daily",
                        start_date=date_str,
                        end_date=date_str,
                        adjust="qfq"
                    )
                
                if not df.empty:
                    price = float(df.iloc[0]['收盘'])
                    if attempt > 0:
                        logger.success(f"Retry succeeded for {normalized_symbol}: ${price}")
                    return price
                else:
                    logger.warning(f"No price data for {normalized_symbol} on {date}")
                    return None
                    
            except Exception as e:
                if normalized_symbol == '04827':  # Known delisted stock - don't retry
                    logger.warning(f"{normalized_symbol} likely delisted/suspended (VISION DEAL)")
                    return None
                
                if attempt == max_retries - 1:  # Last attempt
                    logger.error(f"Failed to get price for {normalized_symbol} after {max_retries} attempts: {e}")
                    return None
                else:
                    logger.warning(f"Attempt {attempt + 1} failed for {normalized_symbol}: {e}")
        
        return None
    
    def get_batch_prices(self, positions: List[Dict], date: str) -> Dict[str, Optional[float]]:
        """
        Get prices for multiple stocks from position data.
        
        Args:
            positions: List of position dicts with 'StockCode' and 'Holding'
            date: Date string like '2024-02-28'
            
        Returns:
            Dict mapping stock_code to price
        """
        stock_codes = [pos['StockCode'] for pos in positions]
        unique_codes = list(set(stock_codes))  # Remove duplicates
        
        logger.info(f"Fetching prices for {len(unique_codes)} unique stocks on {date}")
        
        price_map = {}
        for code in unique_codes:
            price = self.get_single_price(code, date)
            price_map[code] = price
            
        return price_map
    
    def calculate_position_values(self, positions: List[Dict], date: str) -> Dict[str, Dict]:
        """
        Calculate position values for all stocks.
        
        Args:
            positions: List of position dicts with 'StockCode' and 'Holding'
            date: Date string like '2024-02-28'
            
        Returns:
            Dict with position valuations and summary
        """
        if not positions:
            return {
                'positions': [],
                'total_value_usd': 0.0,
                'successful_prices': 0,
                'failed_prices': 0
            }
        
        price_map = self.get_batch_prices(positions, date)
        
        valued_positions = []
        total_value = 0.0
        successful = 0
        failed = 0
        
        for pos in positions:
            stock_code = pos['StockCode']
            holding = pos['Holding']
            price = price_map.get(stock_code)
            
            if price is not None:
                # Assume prices are in local currency, convert to USD if needed
                market_value = holding * price
                successful += 1
            else:
                market_value = 0.0
                failed += 1
            
            valued_position = {
                'StockCode': stock_code,
                'Holding': holding,
                'Price': price,
                'MarketValue': market_value
            }
            valued_positions.append(valued_position)
            total_value += market_value
        
        return {
            'positions': valued_positions,
            'total_value_usd': total_value,  # TODO: Add currency conversion
            'successful_prices': successful,
            'failed_prices': failed
        }
    
    # ========== Option Processing Methods ==========
    
    def parse_option_symbol(self, symbol: str) -> Optional[OptionContract]:
        """
        Parse broker option symbol into structured data.
        
        Examples:
            "TSLA 18JUN26 800 C" -> OptionContract(TSLA, 2026-06-18, 800, C)
            "2318 29SEP25 55 C" -> OptionContract(2318, 2025-09-29, 55, C)
        """
        try:
            # Pattern: SYMBOL DDMMMYY STRIKE C/P
            pattern = r'([A-Z0-9]+)\s+(\d{1,2})([A-Z]{3})(\d{2})\s+([0-9.]+)\s+([CP])'
            match = re.match(pattern, symbol.strip())
            
            if not match:
                logger.debug(f"Option symbol pattern not recognized: {symbol}")
                return None
            
            underlying = match.group(1)
            day = match.group(2).zfill(2)
            month_str = match.group(3)
            year = '20' + match.group(4)  # Convert YY to 20YY
            strike = float(match.group(5))
            option_type = match.group(6)
            
            # Convert month
            month = self.month_map.get(month_str)
            if not month:
                logger.warning(f"Unknown month in option: {month_str}")
                return None
            
            expiry = f"{year}-{month}-{day}"
            
            contract = OptionContract(
                symbol=symbol,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                underlying=underlying
            )
            
            logger.info(f"Parsed option: {symbol} -> {contract}")
            return contract
            
        except Exception as e:
            logger.warning(f"Failed to parse option symbol {symbol}: {e}")
            return None
    
    def is_domestic_option(self, contract: OptionContract) -> bool:
        """
        Check if option is supported by akshare (Chinese options only).
        
        Based on research: akshare ONLY supports Chinese options.
        US/HK options are NOT supported.
        """
        underlying = contract.underlying
        
        # Chinese stock codes
        if underlying.isdigit() and len(underlying) in [4, 5, 6]:
            logger.info(f"Identified potential Chinese stock option: {underlying}")
            return True
        
        # Chinese ETF options  
        if underlying in ['510050', '510300', '159919']:
            logger.info(f"Identified Chinese ETF option: {underlying}")
            return True
        
        # Chinese commodity symbols
        domestic_commodities = [
            'AL', 'CU', 'ZN', 'PB', 'NI', 'SN', 'AU', 'AG',  # 金属
            'RB', 'HC', 'I', 'J', 'JM',  # 黑色
            'A', 'M', 'Y', 'P', 'C', 'CS',  # 农产品
            'TA', 'MA', 'PP', 'PVC', 'L', 'V'  # 化工
        ]
        if underlying.upper() in domestic_commodities:
            logger.info(f"Identified Chinese commodity option: {underlying}")
            return True
        
        # All others (US stocks like TSLA, AAPL) are overseas
        logger.info(f"Identified overseas option (not supported by akshare): {underlying}")
        return False
    
    def get_option_data(self, force_refresh: bool = False) -> Optional[Dict]:
        """Get option market data from akshare with caching."""
        # Check cache (refresh every 5 minutes)
        now = datetime.now()
        if (not force_refresh and 
            self.option_cache is not None and 
            self.cache_timestamp is not None and
            (now - self.cache_timestamp).seconds < 300):
            return self.option_cache
        
        try:
            logger.info("Fetching option market data from akshare...")
            df = ak.option_current_em()
            
            if df.empty:
                logger.warning("No option data returned from akshare")
                return None
            
            # Convert to dict for easier lookup
            option_data = {}
            for _, row in df.iterrows():
                code = row['代码']
                name = row['名称'] 
                price = row['最新价']
                
                option_data[code] = {
                    'name': name,
                    'price': price,
                    'strike': row.get('行权价', None),
                    'volume': row.get('成交量', None)
                }
            
            # Cache the data
            self.option_cache = option_data
            self.cache_timestamp = now
            
            logger.success(f"Loaded {len(option_data)} option contracts")
            return option_data
            
        except Exception as e:
            logger.error(f"Failed to fetch option data: {e}")
            return None
    
    def find_matching_option(self, contract: OptionContract) -> Optional[Tuple[str, float]]:
        """Find matching option in akshare data."""
        # Quick check for overseas options  
        if not self.is_domestic_option(contract):
            logger.info(f"Overseas option detected (akshare不支持美股/港股期权): {contract}")
            return None
        
        option_data = self.get_option_data()
        if not option_data:
            return None
        
        underlying = contract.underlying
        strike = contract.strike
        option_type_cn = '购' if contract.option_type == 'C' else '沽'
        
        # Try different matching strategies
        matches = []
        
        for code, data in option_data.items():
            name = data['name']
            price = data['price']
            
            # Strategy: Direct symbol match in name
            if underlying in name:
                # Check if strike and type match
                if (str(int(strike)) in name and 
                    option_type_cn in name):
                    matches.append((code, price, len(name)))  # Prefer shorter names
        
        if matches:
            # Sort by name length (prefer more specific matches)
            matches.sort(key=lambda x: x[2])
            best_match = matches[0]
            logger.info(f"Found option match: {contract} -> {best_match[0]} @ {best_match[1]}")
            return (best_match[0], best_match[1])
        
        logger.warning(f"No domestic option match found for: {contract}")
        return None
    
    def get_option_price(self, symbol: str) -> Optional[float]:
        """Get option price for a broker option symbol."""
        # Parse the option symbol
        contract = self.parse_option_symbol(symbol)
        if not contract:
            return None
        
        # Find matching option in market data
        match = self.find_matching_option(contract)
        if not match:
            return None
        
        return match[1]  # Return price