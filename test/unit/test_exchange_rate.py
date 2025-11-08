"""
Unit tests for exchange rate caching mechanism.
Focus on cache save/load and lazy loading to reduce API calls.
"""

import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from exchange_rate_handler import ExchangeRateHandler


class TestExchangeRateCaching:
    """Test exchange rate caching mechanism"""
    
    def test_rate_caching_save_and_load(self, tmp_path):
        """Test cache save and load functionality"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        # Save a rate to cache
        handler._save_rate_to_json("CNY", "USD", "2025-02-28", 0.139)
        
        # Verify file was created
        assert cache_file.exists()
        
        # Load the rate back
        rate = handler._load_rate_from_json("CNY", "USD", "2025-02-28")
        assert rate == 0.139
    
    def test_rate_caching_multiple_rates(self, tmp_path):
        """Test caching multiple exchange rates"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        # Save multiple rates
        handler._save_rate_to_json("CNY", "USD", "2025-02-28", 0.139)
        handler._save_rate_to_json("HKD", "USD", "2025-02-28", 0.128)
        handler._save_rate_to_json("CNY", "USD", "2025-06-30", 0.140)
        
        # Verify all rates can be loaded
        assert handler._load_rate_from_json("CNY", "USD", "2025-02-28") == 0.139
        assert handler._load_rate_from_json("HKD", "USD", "2025-02-28") == 0.128
        assert handler._load_rate_from_json("CNY", "USD", "2025-06-30") == 0.140
    
    def test_rate_caching_load_nonexistent(self, tmp_path):
        """Loading non-existent rate returns None"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        rate = handler._load_rate_from_json("EUR", "USD", "2025-02-28")
        assert rate is None
    
    def test_rate_caching_memory_cache(self, tmp_path):
        """Test memory cache functionality"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        # Manually add to memory cache
        handler._rate_cache[("CNY", "USD", "2025-02-28")] = 0.139
        
        # Should retrieve from memory cache
        assert ("CNY", "USD", "2025-02-28") in handler._rate_cache
        assert handler._rate_cache[("CNY", "USD", "2025-02-28")] == 0.139


class TestLazyLoading:
    """Test lazy loading exchange rates"""
    
    def test_lazy_loading_same_currency(self, tmp_path):
        """Same currency conversion returns 1.0"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        rate = handler.get_rate_lazy("USD", "USD", "2025-02-28")
        assert rate == 1.0
    
    def test_lazy_loading_from_cache(self, tmp_path):
        """Lazy loading retrieves from cache if available"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        # Pre-populate cache
        handler._save_rate_to_json("CNY", "USD", "2025-02-28", 0.139)
        
        # Lazy load should use cache
        rate = handler.get_rate_lazy("CNY", "USD", "2025-02-28")
        assert rate == 0.139


class TestCacheStatistics:
    """Test cache statistics and management"""
    
    def test_get_cache_stats(self, tmp_path):
        """Get cache statistics"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        # Initially empty
        stats = handler.get_cache_stats()
        assert stats['memory_cache_size'] == 0
        assert stats['json_cache_size'] == 0
        
        # Add to memory cache
        handler._rate_cache[("CNY", "USD", "2025-02-28")] = 0.139
        
        # Add to JSON cache
        handler._save_rate_to_json("HKD", "USD", "2025-02-28", 0.128)
        
        stats = handler.get_cache_stats()
        assert stats['memory_cache_size'] == 1
        assert stats['json_cache_size'] == 1
    
    def test_clear_cache_memory_only(self, tmp_path):
        """Clear memory cache only"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        # Add data
        handler._rate_cache[("CNY", "USD", "2025-02-28")] = 0.139
        handler._save_rate_to_json("HKD", "USD", "2025-02-28", 0.128)
        
        # Clear memory only
        handler.clear_cache(memory_only=True)
        
        assert len(handler._rate_cache) == 0
        assert cache_file.exists()  # JSON cache still exists
    
    def test_clear_cache_all(self, tmp_path):
        """Clear both memory and JSON cache"""
        cache_file = tmp_path / "test_cache.json"
        handler = ExchangeRateHandler(cache_file=str(cache_file))
        
        # Add data
        handler._rate_cache[("CNY", "USD", "2025-02-28")] = 0.139
        handler._save_rate_to_json("HKD", "USD", "2025-02-28", 0.128)
        
        # Clear all
        handler.clear_cache(memory_only=False)
        
        assert len(handler._rate_cache) == 0
        assert not cache_file.exists()  # JSON cache deleted

