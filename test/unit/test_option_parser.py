"""
Unit tests for option parser registry and key format compatibility.
Focus: US OCC-like option codes and drift between equivalent encodings.
"""

import sys
from pathlib import Path

import pytest

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from option_parser import parse_option
from enums import OptionType


class TestUSOCCParserCompatibility:
    def test_parse_occ_accepts_5_letter_underlying_and_6_digit_strike(self):
        parsed = parse_option("GOOGL270617C500000")
        assert parsed.format_type == "US_OCC"
        assert parsed.underlying == "GOOGL"
        assert parsed.option_type == OptionType.CALL
        assert parsed.expiry_date.strftime("%y%m%d") == "270617"
        assert parsed.strike == pytest.approx(500.0)

    def test_parse_occ_accepts_8_digit_padded_strike(self):
        parsed = parse_option("GOOGL270617C00500000")
        assert parsed.format_type == "US_OCC"
        assert parsed.underlying == "GOOGL"
        assert parsed.option_type == OptionType.CALL
        assert parsed.expiry_date.strftime("%y%m%d") == "270617"
        assert parsed.strike == pytest.approx(500.0)

    def test_parse_occ_equivalent_encodings_produce_same_fields(self):
        a = parse_option("GOOGL270617C500000")
        b = parse_option("GOOGL270617C00500000")
        assert a.format_type == b.format_type == "US_OCC"
        assert a.underlying == b.underlying == "GOOGL"
        assert a.expiry_date == b.expiry_date
        assert a.option_type == b.option_type
        assert a.strike == pytest.approx(b.strike)

