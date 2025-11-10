#!/usr/bin/env python3
"""
Exchange Rate Handler - Centralized exchange rate management
Handles API calls, caching, and currency conversion
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
import requests
import sys

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from src.config import settings


class ExchangeRateHandler:
    """
    Centralized exchange rate management with JSON file caching
    """
    
    def __init__(self, cache_file: str = './out/exchange_rates_cache.json'):
        self.cache_file = Path(cache_file)
        self._rate_cache = {}  # Memory cache: {(from_curr, to_curr, date): rate}
    
    def get_single_rate(self, from_currency: str, to_currency: str, date: str) -> float:
        """Get single exchange rate with dual-layer caching"""
        # Check memory cache first
        cache_key = (from_currency, to_currency, date)
        if cache_key in self._rate_cache:
            logger.debug(f"Using memory cached rate: {from_currency}→{to_currency} = {self._rate_cache[cache_key]}")
            return self._rate_cache[cache_key]
        
        # Check JSON file cache
        rate = self._load_rate_from_json(from_currency, to_currency, date)
        if rate is not None:
            # Store in memory cache too
            self._rate_cache[cache_key] = rate
            logger.debug(f"Using JSON cached rate: {from_currency}→{to_currency} = {rate}")
            return rate
        
        # Not in cache, fetch from API
        try:
            # Rate limiting to prevent 429 errors
            time.sleep(0.6)  # Slightly longer delay to be safe
            
            url = settings.get_exchange_url(from_currency, to_currency, date=date)
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                rate = data.get('result')
                if rate is None or rate <= 0:
                    raise ValueError(f"Invalid exchange rate received: {rate}")
                
                # Cache in both memory and JSON file
                self._rate_cache[cache_key] = rate
                self._save_rate_to_json(from_currency, to_currency, date, rate)
                logger.info(f"Fetched and cached rate: {from_currency}→{to_currency} = {rate}")
                return rate
            else:
                raise ValueError(f"Exchange rate API failed: {data.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Failed to fetch {from_currency}→{to_currency} rate: {e}")
            raise

    def get_rates_dynamic(self, currencies_needed: List[str], target_currency: str = 'USD', date: str = None) -> Dict[str, float]:
        """
        Get exchange rates dynamically based on actual currencies needed
        
        Args:
            currencies_needed: List of currencies found in broker data (e.g., ['HKD', 'CNY', 'EUR'])
            target_currency: Target currency for conversion (default: 'USD')
            date: Date for historical rates
            
        Returns:
            Dict mapping currency to direct conversion rate to target currency
            Example: {'HKD': 0.128, 'CNY': 0.139, 'USD': 1.0} means 1 HKD = 0.128 USD
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # Initialize with target currency
        exchange_rates = {target_currency: 1.0}
        
        # Get unique currencies excluding target
        unique_currencies = list(set(currencies_needed) - {target_currency})
        
        if not unique_currencies:
            logger.info(f"No currency conversion needed, all positions in {target_currency}")
            return exchange_rates
        
        logger.info(f"Fetching dynamic exchange rates for {unique_currencies} → {target_currency} on {date}")
        
        # Fetch rates for each needed currency
        for currency in unique_currencies:
            rate = self.get_single_rate(currency, target_currency, date)
            exchange_rates[currency] = rate
        
        logger.info(f"Exchange rates retrieved: {dict((k, v) for k, v in exchange_rates.items() if k != target_currency)}")
        return exchange_rates

    def get_rates_legacy(self, date: str = None) -> Dict[str, float]:
        """
        Legacy method for backward compatibility
        Uses dynamic fetching for common currencies
        """
        # Common currencies for backward compatibility
        common_currencies = ['CNY', 'HKD']
        return self.get_rates_dynamic(common_currencies, 'USD', date)
    
    def get_rate_lazy(self, from_currency: str, to_currency: str = 'USD', date: str = None) -> float:
        """
        Lazy loading exchange rate - fetch only when needed
        
        Args:
            from_currency: Source currency (e.g., 'HKD', 'CNY')
            to_currency: Target currency (default: 'USD')  
            date: Date for historical rates
            
        Returns:
            Direct conversion rate (from_currency → to_currency)
        """
        if from_currency == to_currency:
            return 1.0
            
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
            
        return self.get_single_rate(from_currency, to_currency, date)

    def convert_to_usd(self, amount: float, currency: str, exchange_rates: Dict[str, float] = None) -> float:
        """Convert specified currency amount to USD using direct conversion rates"""
        if currency == 'USD':
            return amount
        
        # Use provided rates if available
        if exchange_rates and currency in exchange_rates:
            rate = exchange_rates[currency]
            if rate != 1.0:  # Only log if actual conversion happened
                logger.debug(f"Converting {amount} {currency} to USD using rate {rate}")
            return amount * rate  # Direct multiplication since rate is from_currency→USD
        
        logger.warning(f"No exchange rate found for {currency}, using 1:1 conversion (may be inaccurate)")
        return amount

    def _load_rate_from_json(self, from_currency: str, to_currency: str, date: str) -> Optional[float]:
        """Load exchange rate from JSON cache file"""
        if not self.cache_file.exists():
            return None
            
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Create cache key
            key = f"{from_currency}_{to_currency}_{date}"
            return cache_data.get(key)
            
        except Exception as e:
            logger.debug(f"Failed to load from JSON cache: {e}")
            return None
    
    def _save_rate_to_json(self, from_currency: str, to_currency: str, date: str, rate: float) -> None:
        """Save exchange rate to JSON cache file"""
        # Create out directory if it doesn't exist
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Load existing data
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
            else:
                cache_data = {}
            
            # Add new rate
            key = f"{from_currency}_{to_currency}_{date}"
            cache_data[key] = rate
            
            # Save back to file
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2, sort_keys=True)
            
            logger.debug(f"Saved rate to JSON cache: {key} = {rate}")
            
        except Exception as e:
            logger.warning(f"Failed to save to JSON cache: {e}")

    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cached rates"""
        stats = {
            'memory_cache_size': len(self._rate_cache),
            'json_cache_size': 0
        }
        
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                stats['json_cache_size'] = len(cache_data)
            except:
                pass
        
        return stats

    def clear_cache(self, memory_only: bool = False) -> None:
        """Clear exchange rate cache"""
        # Clear memory cache
        self._rate_cache.clear()
        logger.info("Cleared memory exchange rate cache")
        
        # Clear JSON cache if requested
        if not memory_only and self.cache_file.exists():
            self.cache_file.unlink()
            logger.info("Cleared JSON exchange rate cache file")


# Global instance for easy access
exchange_handler = ExchangeRateHandler()
