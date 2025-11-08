"""
Unit tests for core utility functions.
Focus on business logic: option detection, multiplier calculation, MMF detection.
"""

import pytest
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from utils import (
    is_option_contract,
    _identify_hk_option,
    get_option_multiplier,
    calculate_position_value,
    is_money_market_fund
)


class TestOptionDetection:
    """Test option contract detection logic"""
    
    def test_is_option_contract_with_call_keyword(self):
        """Detect options with CALL keyword"""
        assert is_option_contract("AAPL CALL", None) is True
        assert is_option_contract("TSLA 18JUN26 800 CALL", None) is True
    
    def test_is_option_contract_with_put_keyword(self):
        """Detect options with PUT keyword"""
        assert is_option_contract("AAPL PUT", None) is True
        assert is_option_contract("NVDA 15DEC25 500 PUT", None) is True
    
    def test_is_option_contract_with_option_keyword(self):
        """Detect options with OPTION keyword"""
        assert is_option_contract("1810 OPTION", None) is True
        assert is_option_contract("CALL OTC-1810 OPTION", None) is True
    
    def test_is_option_contract_with_single_letter(self):
        """Detect options with single letter C/P suffix"""
        assert is_option_contract("AAPL 26JUN21 150 C", None) is True
        assert is_option_contract("TSLA 18JUN26 800 P", None) is True
    
    def test_is_option_contract_with_occ_format(self):
        """Detect OCC format options"""
        assert is_option_contract("SBET260116P25000", None) is True
        assert is_option_contract("AAPL251219C150000", None) is True
    
    def test_is_option_contract_regular_stock(self):
        """Regular stocks should not be detected as options"""
        assert is_option_contract("AAPL", None) is False
        assert is_option_contract("00700", None) is False
        assert is_option_contract("Apple Inc", None) is False
    
    def test_is_option_contract_with_raw_description(self):
        """Use raw description for detection"""
        assert is_option_contract("XXX", "TSLA CALL OPTION") is True
        assert is_option_contract("XXX", "Regular stock") is False


class TestHKOptionDetection:
    """Test Hong Kong option detection"""
    
    def test_identify_hk_option_hkats_format(self):
        """Detect HKATS format HK options"""
        assert _identify_hk_option("", "CLI 250929 19.00 CALL") is True
        assert _identify_hk_option("", "TCH 260630 25.00 PUT") is True
    
    def test_identify_hk_option_with_hk_suffix(self):
        """Detect HK options with .HK suffix"""
        assert _identify_hk_option("", "(CLI.HK 20250929 CALL 19.0)") is True
    
    def test_identify_hk_option_legacy_format(self):
        """Detect legacy HK option format"""
        assert _identify_hk_option("1810 OPTION", None) is True
        assert _identify_hk_option("0700 OPTION", None) is True
        assert _identify_hk_option("9988 OPTION", None) is True
    
    def test_identify_hk_option_us_option(self):
        """US options should not be detected as HK options"""
        assert _identify_hk_option("AAPL OPTION", None) is False
        assert _identify_hk_option("", "TSLA 18JUN26 800 CALL") is False


class TestOptionMultiplier:
    """Test option multiplier calculation logic"""
    
    def test_get_option_multiplier_broker_provided(self):
        """Broker-provided multiplier has highest priority"""
        result = get_option_multiplier("AAPL CALL", None, broker_multiplier=50)
        assert result == 50
    
    def test_get_option_multiplier_otc_option(self):
        """OTC options always have multiplier 1"""
        result = get_option_multiplier("CALL OTC-1810", "OTC CALL OPTION", None)
        assert result == 1
    
    def test_get_option_multiplier_standard_us_option(self):
        """Standard US options have multiplier 100"""
        result = get_option_multiplier("AAPL 18JUN26 150 CALL", None, None)
        assert result == 100
    
    def test_get_option_multiplier_hk_option_fallback(self):
        """HK options without broker multiplier fallback to 100"""
        result = get_option_multiplier("1810 OPTION", None, None)
        assert result == 100
    
    def test_get_option_multiplier_regular_stock(self):
        """Regular stocks have multiplier 1"""
        result = get_option_multiplier("AAPL", None, None)
        assert result == 1
        
        result = get_option_multiplier("00700", None, None)
        assert result == 1


class TestPositionValueCalculation:
    """Test position value calculation with multiplier"""
    
    def test_calculate_position_value_regular_stock(self):
        """Calculate value for regular stock"""
        value, multiplier = calculate_position_value(
            price=150.50,
            holding=100,
            stock_code="AAPL",
            raw_description=None,
            broker_multiplier=None
        )
        assert value == 15050.0  # 150.50 * 100 * 1
        assert multiplier == 1
    
    def test_calculate_position_value_standard_option(self):
        """Calculate value for standard option with multiplier 100"""
        value, multiplier = calculate_position_value(
            price=5.50,
            holding=10,
            stock_code="AAPL 18JUN26 150 CALL",
            raw_description=None,
            broker_multiplier=None
        )
        assert value == 5500.0  # 5.50 * 10 * 100
        assert multiplier == 100
    
    def test_calculate_position_value_otc_option(self):
        """Calculate value for OTC option with multiplier 1"""
        value, multiplier = calculate_position_value(
            price=28.04,
            holding=100,
            stock_code="CALL OTC-1810",
            raw_description="CALL OTC-1810 EXP 08/26/2026",
            broker_multiplier=None
        )
        assert value == 2804.0  # 28.04 * 100 * 1
        assert multiplier == 1
    
    def test_calculate_position_value_broker_multiplier(self):
        """Calculate value with broker-provided multiplier"""
        value, multiplier = calculate_position_value(
            price=10.00,
            holding=20,
            stock_code="CLI OPTION",
            raw_description=None,
            broker_multiplier=500
        )
        assert value == 100000.0  # 10.00 * 20 * 500
        assert multiplier == 500
    
    def test_calculate_position_value_zero_price(self):
        """Handle zero or negative price"""
        value, multiplier = calculate_position_value(
            price=0,
            holding=100,
            stock_code="AAPL",
            raw_description=None,
            broker_multiplier=None
        )
        assert value == 0.0
        assert multiplier == 1
    
    def test_calculate_position_value_none_price(self):
        """Handle None price"""
        value, multiplier = calculate_position_value(
            price=None,
            holding=100,
            stock_code="AAPL",
            raw_description=None,
            broker_multiplier=None
        )
        assert value == 0.0
        assert multiplier == 1


class TestMMFDetection:
    """Test Money Market Fund detection for cash reclassification"""
    
    def test_is_money_market_fund_csop(self):
        """Detect CSOP money market fund"""
        assert is_money_market_fund("CSOP USD Money Market Fund") is True
    
    def test_is_money_market_fund_case_insensitive(self):
        """Detection should be case insensitive"""
        assert is_money_market_fund("money market fund") is True
        assert is_money_market_fund("MONEY MARKET FUND") is True
        assert is_money_market_fund("Money Market Fund") is True
    
    def test_is_money_market_fund_partial_match(self):
        """Detect MMF in longer descriptions"""
        assert is_money_market_fund("XYZ Money Market Fund Class A") is True
        assert is_money_market_fund("ABC HKD Money Market Fund") is True
    
    def test_is_money_market_fund_regular_stock(self):
        """Regular stocks should not be detected as MMF"""
        assert is_money_market_fund("Apple Inc") is False
        assert is_money_market_fund("AAPL") is False
        assert is_money_market_fund("Tencent Holdings") is False
    
    def test_is_money_market_fund_none(self):
        """Handle None description"""
        assert is_money_market_fund(None) is False
    
    def test_is_money_market_fund_empty_string(self):
        """Handle empty string"""
        assert is_money_market_fund("") is False

