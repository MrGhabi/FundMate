#!/usr/bin/env python3
"""
Configuration settings for FundMate

Centralized configuration with environment variable support.
Simple and practical approach - no over-engineering.
"""

import os
from pathlib import Path


class Settings:
    """Simple configuration class with environment variable support"""
    
    # Directory paths
    OUTPUT_DIR = os.getenv('FUNDMATE_OUTPUT_DIR', './out')
    LOG_DIR = os.getenv('FUNDMATE_LOG_DIR', './log')
    
    # API configuration
    EXCHANGE_API_KEY = os.getenv('EXCHANGE_API_KEY', '4803c190bc2db4046a7ec3007224d1b7')
    # EXCHANGE_API_KEY = os.getenv('EXCHANGE_API_KEY', 'hN2urjneIkW3fKULY2njoM7spGoSC5Pd')
    EXCHANGE_API_BASE = 'https://api.exchangerate.host/convert'
    
    # Price data source configuration - simple global switch
    PRICE_SOURCE = os.getenv('FUNDMATE_PRICE_SOURCE', 'futu')  # 'futu' or 'akshare' only
    
    # Futu OpenD configuration
    FUTU_HOST = os.getenv('FUTU_HOST', '127.0.0.1')
    FUTU_PORT = int(os.getenv('FUTU_PORT', '11111'))
    FUTU_TIMEOUT = int(os.getenv('FUTU_TIMEOUT', '30'))
    
    # Processing defaults
    DEFAULT_MAX_WORKERS = 3
    DEFAULT_DPI = 300
    DEFAULT_IMAGE_FORMAT = 'png'
    
    @property
    def pictures_dir(self) -> str:
        """Output directory for converted images"""
        return f"{self.OUTPUT_DIR}/pictures"
    
    @property
    def result_dir(self) -> str:
        """Output directory for processed results"""
        return f"{self.OUTPUT_DIR}/result"
    
    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist"""
        for dir_path in [self.OUTPUT_DIR, self.LOG_DIR, self.pictures_dir, self.result_dir]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    def get_exchange_url(self, from_currency: str, to_currency: str, amount: int = 1, date: str = None) -> str:
        """Build exchange rate API URL"""
        url = f"{self.EXCHANGE_API_BASE}?access_key={self.EXCHANGE_API_KEY}&from={from_currency}&to={to_currency}&amount={amount}"
        if date:
            url += f"&date={date}"
        return url
    


# Global settings instance
settings = Settings()