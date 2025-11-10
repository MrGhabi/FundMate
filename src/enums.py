"""
Type definitions for the project

This module contains shared type definitions, including enums.
"""
from enum import Enum


class PositionContext(Enum):
    """
    Position context indicating where the position data comes from
    
    BASE: Position from broker statement PDF (base portfolio snapshot)
    TC: Position from trade confirmation (transaction-based changes)
    """
    BASE = "base"
    TC = "tc"
    
    def __str__(self):
        """String representation returns the enum value for compatibility"""
        return self.value


class OptionType(Enum):
    """
    Option type: CALL or PUT
    
    Only two possible values, fixed forever. Using enum provides:
    - Type safety (no typos like "CAL" or "CALLL")
    - IDE autocomplete and refactoring support
    - Clear intent in code
    """
    CALL = "CALL"
    PUT = "PUT"
    
    def __str__(self):
        """String representation returns the enum value"""
        return self.value
    
    def __eq__(self, other):
        """
        Support comparison with strings for backward compatibility
        
        Examples:
            OptionType.CALL == "CALL"  # True
            OptionType.CALL == "call"  # True
            OptionType.PUT == "PUT"    # True
        """
        if isinstance(other, str):
            return self.value == other.upper()
        return super().__eq__(other)
    
    @classmethod
    def from_string(cls, value: str) -> 'OptionType':
        """
        Create OptionType from string, case-insensitive
        
        Args:
            value: "CALL", "call", "C" or "PUT", "put", "P"
            
        Returns:
            OptionType.CALL or OptionType.PUT
            
        Raises:
            ValueError: If value is not valid option type
        """
        if not value:
            raise ValueError("Option type cannot be empty")
        
        upper_value = value.upper()
        
        # Support both full names and single letters
        if upper_value in ('CALL', 'C'):
            return cls.CALL
        elif upper_value in ('PUT', 'P'):
            return cls.PUT
        else:
            raise ValueError(f"Invalid option type: {value}. Expected CALL/C or PUT/P")

