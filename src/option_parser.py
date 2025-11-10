"""
Option Parser Module

Provides a pluggable parser architecture for handling various option formats.
Uses ABC pattern for parser interface and registry pattern for extensibility.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, List, Union
import re
from loguru import logger
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from src.enums import OptionType


@dataclass
class ParsedOption:
    """
    Unified parsed option result
    
    Represents the standardized output from any option parser.
    Uses OptionType enum for type safety.
    """
    format_type: str  # 'US_OCC' / 'HK_HKATS' / 'OTC' / 'UNPARSEABLE'
    original_code: str
    
    # Core option fields (None for non-options or unparseable)
    underlying: Optional[str] = None  # Ticker or HKATS code
    expiry_date: Optional[date] = None
    strike: Optional[float] = None
    option_type: Optional[OptionType] = None  # OptionType.CALL or OptionType.PUT
    
    # Market attributes
    multiplier: int = 1
    currency: str = 'USD'
    
    # HK-specific fields
    hk_numeric_code: Optional[str] = None
    hkats_resolved: bool = False
    
    @property
    def option_type_str(self) -> Optional[str]:
        """Return option type as string for backward compatibility"""
        return str(self.option_type) if self.option_type else None


class OptionParser(ABC):
    """
    Abstract base class for option parsers
    
    All concrete parsers must implement can_parse() and parse() methods.
    """
    
    @abstractmethod
    def can_parse(self, code: str) -> bool:
        """
        Check if this parser can handle the given code
        
        Args:
            code: Option code string to check
            
        Returns:
            True if this parser can parse the code
        """
        pass
    
    @abstractmethod
    def parse(self, code: str) -> ParsedOption:
        """
        Parse the code and return structured result
        
        Args:
            code: Option code string to parse
            
        Returns:
            ParsedOption with extracted fields
            
        Raises:
            ValueError: If parsing fails
        """
        pass


class ParserRegistry:
    """
    Central registry for all option parsers
    
    Maintains an ordered list of parsers and dispatches parsing requests
    to them in registration order.
    """
    
    def __init__(self):
        self._parsers: List[OptionParser] = []
    
    def register(self, parser: OptionParser):
        """
        Register a parser (order matters!)
        
        Parsers are tried in registration order, so register high-priority
        parsers (like OTC detection) first.
        """
        self._parsers.append(parser)
    
    def parse(self, code: str) -> ParsedOption:
        """
        Try all registered parsers in order until one succeeds
        
        Args:
            code: Option code to parse
            
        Returns:
            ParsedOption from first successful parser, or UNPARSEABLE
        """
        for parser in self._parsers:
            if parser.can_parse(code):
                try:
                    return parser.parse(code)
                except Exception as e:
                    logger.warning(f"{parser.__class__.__name__} failed on '{code}': {e}")
                    continue
        
        # No parser succeeded
        return ParsedOption(
            format_type='UNPARSEABLE',
            original_code=code
        )


class OTCParser(OptionParser):
    """
    Parse OTC (Over-The-Counter) options
    
    OTC options are kept as-is without standardization.
    Examples:
      - "CALL OTC-0388 1.0@350.0 EXP 09/21/2026 HKEX (EURO)"
      - "3690.HK 180 28May27 CE OTC"
    """
    
    def can_parse(self, code: str) -> bool:
        """Check if code contains OTC keywords"""
        otc_keywords = ['OTC', 'EURO', 'AMERICAN']
        return any(kw in code.upper() for kw in otc_keywords)
    
    def parse(self, code: str) -> ParsedOption:
        """Keep OTC format as-is, extract minimal info"""
        # Try to extract ticker for currency inference
        ticker = None
        if 'OTC-' in code:
            m = re.search(r'OTC-(\d{4})', code)
            if m:
                ticker = m.group(1)
        
        currency = 'HKD' if ticker and ticker.isdigit() else 'USD'
        
        return ParsedOption(
            format_type='OTC',
            original_code=code,
            multiplier=1,  # OTC multiplier usually from broker
            currency=currency
        )


class USOCCParser(OptionParser):
    """
    Parse US OCC (Options Clearing Corporation) format
    
    Format: TICKER + YYMMDD + C/P + STRIKE*1000 (5 digits)
    Example: SBET260116P41000
      - SBET: ticker
      - 260116: expiry 2026-01-16
      - P: PUT
      - 41000: strike $41.0 * 1000
    """
    
    def can_parse(self, code: str) -> bool:
        """Check if matches OCC format"""
        return bool(re.match(r'^[A-Z]{1,4}\d{6}[CP]\d{5}$', code))
    
    def parse(self, code: str) -> ParsedOption:
        """Parse OCC format"""
        match = re.match(r'^([A-Z]{1,4})(\d{2})(\d{2})(\d{2})([CP])(\d{5})$', code)
        if not match:
            raise ValueError(f"Invalid OCC format: {code}")
        
        ticker, yy, mm, dd, cp, strike_int = match.groups()
        
        # Convert to date
        year = 2000 + int(yy)
        expiry = date(year, int(mm), int(dd))
        
        return ParsedOption(
            format_type='US_OCC',
            original_code=code,
            underlying=ticker,
            expiry_date=expiry,
            strike=int(strike_int) / 1000.0,
            option_type=OptionType.CALL if cp == 'C' else OptionType.PUT,
            multiplier=100,
            currency='USD'
        )


class HKHKATSParser(OptionParser):
    """
    Parse HK HKATS (Hong Kong Automated Trading System) format
    
    Format: HKATS_CODE + space + YYMMDD + space + STRIKE + space + CALL/PUT
    Example: CLI 260629 20.00 CALL
      - CLI: HKATS letter code
      - 260629: expiry 2026-06-29
      - 20.00: strike HK$20.0
      - CALL: option type
    
    Also handles: "(CLI.HK 20260629 CALL 20.0)"
    """
    
    def can_parse(self, code: str) -> bool:
        """Check if matches HKATS format"""
        patterns = [
            r'^[A-Z]{3}\s+\d{6}\s+\d+\.?\d*\s+(CALL|PUT)$',  # CLI 260629 20.00 CALL
            r'^\([A-Z]{3}\.HK\s+\d{8}\s+(CALL|PUT)\s+\d+\.?\d*\)$',  # (CLI.HK 20260629 CALL 20.0)
        ]
        return any(re.match(p, code.upper()) for p in patterns)
    
    def parse(self, code: str) -> ParsedOption:
        """Parse HKATS format"""
        upper_code = code.upper()
        
        # Pattern 1: CLI 260629 20.00 CALL
        m1 = re.match(r'^([A-Z]{3})\s+(\d{6})\s+(\d+\.?\d*)\s+(CALL|PUT)$', upper_code)
        if m1:
            hkats, yymmdd, strike, opt_type = m1.groups()
            yy, mm, dd = yymmdd[:2], yymmdd[2:4], yymmdd[4:6]
            expiry = date(2000 + int(yy), int(mm), int(dd))
            
            return ParsedOption(
                format_type='HK_HKATS',
                original_code=code,
                underlying=hkats,
                expiry_date=expiry,
                strike=float(strike),
                option_type=OptionType.from_string(opt_type),
                multiplier=1000,
                currency='HKD',
                hkats_resolved=True
            )
        
        # Pattern 2: (CLI.HK 20260629 CALL 20.0)
        m2 = re.match(r'^\(([A-Z]{3})\.HK\s+(\d{8})\s+(CALL|PUT)\s+(\d+\.?\d*)\)$', upper_code)
        if m2:
            hkats, yyyymmdd, opt_type, strike = m2.groups()
            expiry = datetime.strptime(yyyymmdd, '%Y%m%d').date()
            
            return ParsedOption(
                format_type='HK_HKATS',
                original_code=code,
                underlying=hkats,
                expiry_date=expiry,
                strike=float(strike),
                option_type=OptionType.from_string(opt_type),
                multiplier=1000,
                currency='HKD',
                hkats_resolved=True
            )
        
        raise ValueError(f"Cannot parse HKATS format: {code}")


class USLongFormatParser(OptionParser):
    """
    Parse US long format from TC files
    
    Format: TICKER + [US] + MM/DD/YY + C/P + STRIKE
    Examples:
      - "SBET US 01/16/26 P41"
      - "AMZN US 06/18/26 C300"
    """
    
    def can_parse(self, code: str) -> bool:
        """Check TC long format"""
        return bool(re.match(r'^[A-Z]+\s+US\s+\d{2}/\d{2}/\d{2}\s+[CP]\d+', code.upper()))
    
    def parse(self, code: str) -> ParsedOption:
        """Parse and convert to OCC"""
        m = re.match(r'^([A-Z]+)\s+US\s+(\d{2})/(\d{2})/(\d{2})\s+([CP])(\d+\.?\d*)$', code.upper())
        if not m:
            raise ValueError(f"Invalid US long format: {code}")
        
        ticker, mm, dd, yy, cp, strike = m.groups()
        year = 2000 + int(yy)
        expiry = date(year, int(mm), int(dd))
        
        return ParsedOption(
            format_type='US_OCC',
            original_code=code,
            underlying=ticker,
            expiry_date=expiry,
            strike=float(strike),
            option_type=OptionType.CALL if cp == 'C' else OptionType.PUT,
            multiplier=100,
            currency='USD'
        )


class HKNumericParser(OptionParser):
    """
    Parse HK numeric code format and resolve to HKATS via API
    
    Formats:
      - "2628 HK 06/29/26 C20" (TC format)
      - "2318 29SEP25 55 C" (IB format)
    
    Requires Futu API to resolve numeric code (e.g., 2628) to HKATS code (e.g., CLI).
    Can optionally inject a resolve function for testing or custom resolution logic.
    """
    
    def __init__(self, resolve_func=None):
        """
        Initialize HKNumericParser
        
        Args:
            resolve_func: Optional callable(numeric_code: str) -> str
                          that resolves numeric code to HKATS letter code.
                          If not provided, resolution will be skipped.
        """
        self._cache = {}  # In-memory cache for resolved codes
        self._resolve_func = resolve_func
    
    def can_parse(self, code: str) -> bool:
        """Check if contains numeric HK code with date pattern"""
        patterns = [
            r'^\d{4}\s+(HK|C1)\s+\d{2}/\d{2}/\d{2}\s+[CP]\d+',  # 2628 HK 06/29/26 C20
            r'^\d{4}\s+\d{2}[A-Z]{3}\d{2}\s+\d+\.?\d*\s+[CP]',  # 2318 29SEP25 55 C
        ]
        return any(re.search(p, code.upper()) for p in patterns)
    
    def parse(self, code: str) -> ParsedOption:
        """Parse and resolve HK numeric code via Futu API"""
        # Pattern 1: 2628 HK 06/29/26 C20
        m1 = re.match(r'^(\d{4})\s+(HK|C1)\s+(\d{2})/(\d{2})/(\d{2})\s+([CP])(\d+\.?\d*)$', code.upper())
        if m1:
            numeric, market, mm, dd, yy, cp, strike = m1.groups()
            year = 2000 + int(yy)
            expiry = date(year, int(mm), int(dd))
            strike_float = float(strike)
            opt_type_enum = OptionType.CALL if cp == 'C' else OptionType.PUT
            
            # Try to resolve HKATS code via API (pass string for backward compatibility)
            hkats_code = self._resolve_hkats(numeric, expiry, strike_float, str(opt_type_enum))
            
            return ParsedOption(
                format_type='HK_HKATS',
                original_code=code,
                underlying=hkats_code if hkats_code else numeric,
                expiry_date=expiry,
                strike=strike_float,
                option_type=opt_type_enum,
                multiplier=1000,
                currency='HKD',
                hk_numeric_code=numeric,
                hkats_resolved=bool(hkats_code)
            )
        
        # Pattern 2: 2318 29SEP25 55 C
        m2 = re.match(r'^(\d{4})\s+(\d{2})([A-Z]{3})(\d{2})\s+(\d+\.?\d*)\s+([CP])$', code.upper())
        if m2:
            numeric, dd, mon_str, yy, strike, cp = m2.groups()
            
            month_map = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            month = month_map.get(mon_str)
            if not month:
                raise ValueError(f"Unknown month: {mon_str}")
            
            year = 2000 + int(yy)
            expiry = date(year, month, int(dd))
            strike_float = float(strike)
            opt_type_enum = OptionType.CALL if cp == 'C' else OptionType.PUT
            
            hkats_code = self._resolve_hkats(numeric, expiry, strike_float, str(opt_type_enum))
            
            return ParsedOption(
                format_type='HK_HKATS',
                original_code=code,
                underlying=hkats_code if hkats_code else numeric,
                expiry_date=expiry,
                strike=strike_float,
                option_type=opt_type_enum,
                multiplier=1000,
                currency='HKD',
                hk_numeric_code=numeric,
                hkats_resolved=bool(hkats_code)
            )
        
        raise ValueError(f"Cannot parse HK numeric format: {code}")
    
    def _resolve_hkats(self, numeric: str, expiry: date, strike: float, opt_type: str) -> Optional[str]:
        """
        Resolve numeric code to HKATS via Futu API
        
        Returns:
            HKATS code (e.g., 'CLI') or None if resolution fails
        """
        # If no resolve function was injected, skip resolution
        if not self._resolve_func:
            logger.debug(f"No resolve function provided for HKNumericParser, skipping HKATS resolution for {numeric}")
            return None
        
        cache_key = f"{numeric}_{expiry}_{strike}_{opt_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            # Call injected resolve function
            hkats_code = self._resolve_func(numeric)
            self._cache[cache_key] = hkats_code
            logger.info(f"Resolved {numeric} → {hkats_code} via Futu API")
            return hkats_code
        except Exception as e:
            logger.warning(f"HKATS resolution failed for {numeric}: {e}")
            return None


# Global registry instance
_registry = ParserRegistry()


def register_parser(parser: OptionParser):
    """Register a parser to the global registry"""
    _registry.register(parser)


def parse_option(code: str) -> ParsedOption:
    """
    Main entry point for parsing options
    
    Args:
        code: Option code string to parse
        
    Returns:
        ParsedOption with extracted fields
    """
    return _registry.parse(code)


def _init_default_parsers():
    """
    Register parsers in priority order
    
    Order matters! Parsers are tried in registration sequence:
    1. OTC must be first (to prevent misidentification as standard options)
    2. Already-standardized formats (OCC, HKATS letter code) next
    3. Long formats that need conversion
    4. Numeric HK - NOT registered by default, requires API resolve function
       (will be registered by TradeConfirmationProcessor with resolve_func injected)
    """
    register_parser(OTCParser())              # 1. Detect OTC first
    register_parser(USOCCParser())            # 2. US already in OCC format
    register_parser(HKHKATSParser())          # 3. HK already in HKATS format
    register_parser(USLongFormatParser())     # 4. US long format from TC
    # HKNumericParser NOT registered here - requires resolve_func dependency injection


# Auto-initialize default parsers on module import
_init_default_parsers()
