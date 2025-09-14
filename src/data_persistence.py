"""
Data persistence module for broker statement processing results.
Saves processed broker data using Pandas and Parquet format for efficient storage and analysis.
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from loguru import logger
from image_processor import ProcessedResult


class DataPersistence:
    """
    Handles saving and loading of processed broker data using Pandas and Parquet format.
    Organizes data by date for easy time-series analysis.
    """
    
    def __init__(self, base_output_dir: str = "./out/result"):
        """
        Initialize the data persistence handler.
        
        Args:
            base_output_dir: Base directory for saving processed data
        """
        self.base_output_dir = Path(base_output_dir)
        
    def _ensure_directory(self, directory: Path) -> None:
        """
        Ensure directory exists, create if necessary.
        
        Args:
            directory: Directory path to create
        """
        directory.mkdir(parents=True, exist_ok=True)
        
    def _get_date_directory(self, date: str) -> Path:
        """
        Get the directory path for a specific date.
        
        Args:
            date: Date string in YYYY-MM-DD format
            
        Returns:
            Path: Directory path for the date
        """
        return self.base_output_dir / date
        
    def save_broker_data(self, results: List[ProcessedResult], date: str, 
                        exchange_rates: Dict[str, float]) -> Dict[str, str]:
        """
        Save processed broker data to Parquet files organized by date.
        
        Args:
            results: List of ProcessedResult objects from broker processing
            date: Date string in YYYY-MM-DD format
            exchange_rates: Currency exchange rates used for processing
            
        Returns:
            Dict[str, str]: Dictionary with file paths of saved data
        """
        if not results:
            logger.warning(f"No results to save for date: {date}")
            return {}
            
        date_dir = self._get_date_directory(date)
        self._ensure_directory(date_dir)
        
        logger.info(f"Saving {len(results)} broker results to {date_dir}")
        
        # Prepare cash summary data
        cash_data = []
        positions_data = []
        
        for result in results:
            # Extract cash data
            cash_row = {
                'date': date,
                'broker_name': result.broker_name,
                'account_id': result.account_id,
                'cny': result.cash_data.get('CNY'),
                'hkd': result.cash_data.get('HKD'),
                'usd': result.cash_data.get('USD'),
                'total': result.cash_data.get('Total'),
                'total_type': result.cash_data.get('Total_type'),
                'usd_total': result.usd_total,
                'timestamp': datetime.now().isoformat()
            }
            cash_data.append(cash_row)
            
            # Extract positions data
            for position in result.positions:
                # Convert holding to integer, handle string values with commas
                holding_value = position['Holding']
                if isinstance(holding_value, str):
                    # Remove commas and convert to int
                    holding_value = int(holding_value.replace(',', ''))
                else:
                    holding_value = int(holding_value)
                
                position_row = {
                    'date': date,
                    'broker_name': result.broker_name,
                    'account_id': result.account_id,
                    'stock_code': position['StockCode'],
                    'holding': holding_value,
                    'timestamp': datetime.now().isoformat()
                }
                positions_data.append(position_row)
        
        # Save cash summary to Parquet
        cash_df = pd.DataFrame(cash_data)
        cash_file = date_dir / f"cash_summary_{date}.parquet"
        cash_df.to_parquet(cash_file, index=False, compression='snappy')
        logger.info(f"Cash summary saved: {cash_file}")
        
        # Save positions to Parquet
        positions_df = pd.DataFrame(positions_data)
        positions_file = date_dir / f"positions_{date}.parquet"
        positions_df.to_parquet(positions_file, index=False, compression='snappy')
        logger.info(f"Positions data saved: {positions_file}")
        
        # Save metadata as JSON
        metadata = {
            'date': date,
            'timestamp': datetime.now().isoformat(),
            'broker_count': len(results),
            'total_positions': len(positions_data),
            'exchange_rates': exchange_rates,
            'brokers_processed': [result.broker_name for result in results],
            'files': {
                'cash_summary': cash_file.name,
                'positions': positions_file.name
            }
        }
        
        metadata_file = date_dir / f"metadata_{date}.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logger.info(f"Metadata saved: {metadata_file}")
        
        # Generate summary statistics
        total_usd = cash_df['usd_total'].sum()
        unique_brokers = cash_df['broker_name'].nunique()
        total_stocks = positions_df['stock_code'].nunique() if not positions_df.empty else 0
        
        logger.success(f"Data persistence completed for {date}")
        logger.info(f"Summary - Brokers: {unique_brokers}, Total USD: ${total_usd:,.2f}, Unique Stocks: {total_stocks}")
        
        return {
            'cash_summary': str(cash_file),
            'positions': str(positions_file),
            'metadata': str(metadata_file)
        }
    
    def load_broker_data(self, date: str) -> Optional[Dict[str, pd.DataFrame]]:
        """
        Load processed broker data for a specific date.
        
        Args:
            date: Date string in YYYY-MM-DD format
            
        Returns:
            Dict[str, pd.DataFrame]: Dictionary containing 'cash' and 'positions' DataFrames,
                                   or None if data not found
        """
        date_dir = self._get_date_directory(date)
        
        if not date_dir.exists():
            logger.warning(f"No data directory found for date: {date}")
            return None
            
        cash_file = date_dir / f"cash_summary_{date}.parquet"
        positions_file = date_dir / f"positions_{date}.parquet"
        
        try:
            result = {}
            
            if cash_file.exists():
                result['cash'] = pd.read_parquet(cash_file)
                logger.info(f"Loaded cash data: {len(result['cash'])} records")
            else:
                logger.warning(f"Cash summary file not found: {cash_file}")
                
            if positions_file.exists():
                result['positions'] = pd.read_parquet(positions_file)
                logger.info(f"Loaded positions data: {len(result['positions'])} records")
            else:
                logger.warning(f"Positions file not found: {positions_file}")
                
            return result if result else None
            
        except Exception as e:
            logger.error(f"Error loading data for date {date}: {e}")
            return None
    
    def get_available_dates(self) -> List[str]:
        """
        Get list of available dates with saved data.
        
        Returns:
            List[str]: List of date strings in YYYY-MM-DD format
        """
        if not self.base_output_dir.exists():
            return []
            
        dates = []
        for item in self.base_output_dir.iterdir():
            if item.is_dir() and len(item.name) == 10:  # YYYY-MM-DD format
                try:
                    # Validate date format
                    datetime.strptime(item.name, '%Y-%m-%d')
                    dates.append(item.name)
                except ValueError:
                    continue
                    
        return sorted(dates)



# Utility function for easy integration
def save_processing_results(results: List[ProcessedResult], date: str, 
                          exchange_rates: Dict[str, float],
                          output_dir: str = "./out/result") -> Dict[str, str]:
    """
    Convenience function to save processing results.
    
    Args:
        results: List of ProcessedResult objects
        date: Date string in YYYY-MM-DD format
        exchange_rates: Currency exchange rates
        output_dir: Output directory for saved data
        
    Returns:
        Dict[str, str]: Dictionary with file paths of saved data
    """
    persistence = DataPersistence(output_dir)
    return persistence.save_broker_data(results, date, exchange_rates) 