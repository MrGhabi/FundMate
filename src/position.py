"""
Position Module

Defines the unified Position class for representing portfolio positions.
Automatically parses option contracts on initialization.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import date
import logging
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from src.enums import PositionContext, OptionType
from src.option_parser import parse_option

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """
    Unified position data structure with automatic option parsing
    
    Represents a single position in a portfolio, whether it's a stock or option.
    For options, parsing is automatically performed during initialization to extract
    underlying, strike, expiry, etc.
    """
    # Core business fields
    stock_code: str
    holding: float
    broker: str
    context: PositionContext = PositionContext.BASE
    
    # Price fields
    broker_price: Optional[float] = None
    final_price: Optional[float] = None
    final_price_source: str = ''
    price_currency: Optional[str] = None
    optimized_price_currency: str = 'USD'
    
    # Description
    raw_description: Optional[str] = None
    
    # Stock/Option attributes
    multiplier: Optional[int] = None
    
    # Option parsing fields (auto-populated in __post_init__)
    option_format: Optional[str] = field(default=None, init=False)  # US_OCC/HK_HKATS/OTC/UNPARSEABLE
    underlying: Optional[str] = field(default=None, init=False)
    expiry_date: Optional[date] = field(default=None, init=False)
    strike: Optional[float] = field(default=None, init=False)
    option_type: Optional[OptionType] = field(default=None, init=False)  # OptionType.CALL or OptionType.PUT
    hk_numeric_code: Optional[str] = field(default=None, init=False)
    hkats_resolved: bool = field(default=False, init=False)
    
    @property
    def option_type_str(self) -> Optional[str]:
        """Return option type as string for backward compatibility"""
        return str(self.option_type) if self.option_type else None
    
    def __post_init__(self):
        """Automatically parse option if detected"""
        self._parse_option_if_needed()
    
    def _parse_option_if_needed(self):
        """
        Parse option format and populate fields if this is an option contract
        
        Tries to parse the stock_code directly. If it's not an option,
        the parser will return UNPARSEABLE and we simply don't populate fields.
        """
        try:
            parsed = parse_option(self.stock_code)
            
            # Only populate if successfully parsed (not UNPARSEABLE)
            if parsed.format_type != 'UNPARSEABLE':
                self.option_format = parsed.format_type
                self.underlying = parsed.underlying
                self.expiry_date = parsed.expiry_date
                self.strike = parsed.strike
                self.option_type = parsed.option_type
                self.hk_numeric_code = parsed.hk_numeric_code
                self.hkats_resolved = parsed.hkats_resolved
                
                # Use parsed multiplier if not already set
                if self.multiplier is None:
                    self.multiplier = parsed.multiplier
        except Exception as e:
            logger.warning(f"Failed to parse option {self.stock_code}: {e}")
    
    def to_dict(self) -> dict:
        """
        Convert to dict for DataFrame/Parquet/CSV output
        
        Only exports business fields, not internal parsing fields.
        CSV will show option codes as-is (e.g., SBET260116P41000 or CLI 260629 20 CALL),
        not the parsed components (underlying, strike, etc).
        """
        return {
            'StockCode': self.stock_code,
            'RawDescription': self.raw_description,
            'Holding': self.holding,
            'BrokerPrice': self.broker_price,
            'PriceCurrency': self.price_currency,
            'FinalPrice': self.final_price,
            'FinalPriceSource': self.final_price_source,
            'OptimizedPriceCurrency': self.optimized_price_currency,
            'Multiplier': self.multiplier
        }
    
    def matches_option(self, other: 'Position') -> bool:
        """
        Check if this option matches another (for fuzzy matching)
        
        Replaces 130+ lines of complex fuzzy matching logic with simple field comparison.
        
        Returns True if:
        - Exact stock_code match, OR
        - Both are standard options with matching parsed fields
        
        Args:
            other: Another Position to compare with
            
        Returns:
            True if positions match (same option contract)
        """
        # Fast path: exact stock_code match
        if self.stock_code == other.stock_code:
            return True
        
        # Both must be options
        if not self.option_format or not other.option_format:
            return False
        
        # UNPARSEABLE options cannot match
        if self.option_format == 'UNPARSEABLE' or other.option_format == 'UNPARSEABLE':
            return False
        
        # OTC options: only exact stock_code match (already checked above)
        if self.option_format == 'OTC' or other.option_format == 'OTC':
            return False
        
        # Standard options: compare parsed fields
        # Use 0.01 threshold for strike to handle floating point precision
        return (
            self.underlying == other.underlying and
            self.expiry_date == other.expiry_date and
            abs(self.strike - other.strike) < 0.01 and
            self.option_type == other.option_type
        )
