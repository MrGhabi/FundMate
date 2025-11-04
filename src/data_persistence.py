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

try:
    from .broker_processor import ProcessedResult
    from .config import settings
except (ImportError, ValueError):
    from broker_processor import ProcessedResult
    from config import settings

try:
    from .utils import is_money_market_fund, calculate_position_value
except (ImportError, ValueError):
    from utils import is_money_market_fund, calculate_position_value


class DataPersistence:
    """
    Handles saving and loading of processed broker data using Pandas and Parquet format.
    Organizes data by date for easy time-series analysis.
    """
    
    def __init__(self, base_output_dir: str = None):
        if base_output_dir is None:
            base_output_dir = settings.result_dir
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
            # ========== MMF Reclassification ==========
            # Detect and move Money Market Funds from positions to cash
            real_positions = []
            mmf_cash_adjustments = {}
            
            for position in result.positions:
                description = position.get('RawDescription', '')
                
                # Check if this is a MMF
                if is_money_market_fund(description):
                    # Calculate value
                    holding = position.get('Holding', 0)
                    if isinstance(holding, str):
                        holding = float(holding.replace(',', ''))
                    else:
                        holding = float(holding)
                    
                    price = position.get('Price', 0)
                    if isinstance(price, str):
                        price = float(price.replace(',', ''))
                    else:
                        price = float(price)
                    
                    value = holding * price
                    currency = position.get('PriceCurrency', 'USD')
                    
                    # Accumulate cash adjustment
                    if currency not in mmf_cash_adjustments:
                        mmf_cash_adjustments[currency] = 0
                    mmf_cash_adjustments[currency] += value
                    
                    logger.info(
                        f"💰 Reclassified MMF to cash: {position.get('StockCode')} "
                        f"- {description} = {currency} {value:,.2f}"
                    )
                else:
                    # Keep as position
                    real_positions.append(position)
            
            # Apply cash adjustments
            for currency, value in mmf_cash_adjustments.items():
                current_cash = result.cash_data.get(currency, 0) or 0
                result.cash_data[currency] = float(current_cash) + value
                logger.success(
                    f"✅ Added {currency} {value:,.2f} from MMF to cash "
                    f"(total: {result.cash_data[currency]:,.2f})"
                )
            
            # Update positions (exclude MMFs)
            result.positions = real_positions
            
            # Recalculate usd_total after MMF reclassification
            if mmf_cash_adjustments:
                usd_total = 0.0
                usd_total += float(result.cash_data.get('USD', 0) or 0)
                
                # Convert HKD to USD
                hkd = result.cash_data.get('HKD', 0) or 0
                if hkd and 'HKD' in exchange_rates:
                    usd_total += float(hkd) * exchange_rates['HKD']
                
                # Convert CNY to USD
                cny = result.cash_data.get('CNY', 0) or 0
                if cny and 'CNY' in exchange_rates:
                    usd_total += float(cny) * exchange_rates['CNY']
                
                result.usd_total = usd_total
                logger.info(f"🔄 Recalculated usd_total after MMF reclassification: ${usd_total:,.2f}")
            # ========== End MMF Reclassification ==========
            
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
                
                # Calculate USD value using the same logic as print_asset_summary
                position_value_usd = None
                if position.get('FinalPrice'):
                    try:
                        position_value, _ = calculate_position_value(
                            price=position['FinalPrice'],
                            holding=holding_value,
                            stock_code=position['StockCode'],
                            raw_description=position.get('RawDescription'),
                            broker_multiplier=position.get('Multiplier')
                        )
                        
                        # Convert to USD if needed
                        price_currency = position.get('OptimizedPriceCurrency', 'USD')
                        if price_currency != 'USD' and position_value != 0:
                            rate = exchange_rates.get(price_currency, 1.0)
                            position_value_usd = position_value * rate
                        else:
                            position_value_usd = position_value
                            
                    except Exception as e:
                        logger.warning(f"Failed to calculate value for {position['StockCode']}: {e}")
                
                position_row = {
                    # Basic info
                    'date': date,
                    'broker_name': result.broker_name,
                    'account_id': result.account_id,
                    
                    # Position info
                    'stock_code': position['StockCode'],
                    'raw_description': position.get('RawDescription', ''),
                    'holding': holding_value,
                    
                    # Price info
                    'broker_price': position.get('BrokerPrice'),
                    'broker_price_currency': position.get('PriceCurrency'),
                    'final_price': position.get('FinalPrice'),
                    'final_price_source': position.get('FinalPriceSource'),
                    'optimized_price_currency': position.get('OptimizedPriceCurrency'),
                    
                    # Option info
                    'multiplier': position.get('Multiplier', 1),
                    
                    # Calculated value
                    'position_value_usd': position_value_usd,
                    
                    'timestamp': datetime.now().isoformat()
                }
                positions_data.append(position_row)
        
        # Save cash summary to Parquet with detailed logging
        cash_df = pd.DataFrame(cash_data)
        cash_file = date_dir / f"cash_summary_{date}.parquet"
        cash_df.to_parquet(cash_file, index=False, compression='snappy')
        
        # Log file save confirmation
        logger.info(f"💾 Cash summary saved: {cash_file}")
        
        # Save positions to Parquet with detailed logging
        positions_df = pd.DataFrame(positions_data)
        positions_file = date_dir / f"positions_{date}.parquet"
        positions_df.to_parquet(positions_file, index=False, compression='snappy')
        
        # Log file save confirmation
        logger.info(f"💾 Positions data saved: {positions_file}")
        
        # Export comprehensive CSV report (exclude timestamp for cleaner output)
        csv_file = date_dir / f"portfolio_details_{date}.csv"
        csv_df = positions_df.drop(columns=['timestamp']).copy()
        # Round position_value_usd to 2 decimal places
        csv_df['position_value_usd'] = csv_df['position_value_usd'].round(2)
        
        # Calculate totals for summary rows
        total_cash = cash_df['usd_total'].sum()
        
        # Calculate deduplicated position total (cross-broker aggregation)
        # Group by stock_code/raw_description and sum position values to avoid double-counting
        position_aggregation = {}
        for position_row in positions_data:
            stock_code = position_row['stock_code']
            raw_desc = position_row.get('raw_description', '')
            
            # Use raw_description for options to distinguish different contracts
            if raw_desc and 'OPTION' in stock_code.upper():
                unique_key = raw_desc
            else:
                unique_key = stock_code
            
            # Sum position values across brokers
            position_value = position_row.get('position_value_usd', 0) or 0
            if unique_key not in position_aggregation:
                position_aggregation[unique_key] = 0
            position_aggregation[unique_key] += position_value
        
        # Total positions is the sum of deduplicated position values
        total_positions = sum(position_aggregation.values())
        grand_total = total_cash + total_positions
        
        # Add summary rows at the end
        summary_rows = pd.DataFrame([
            {
                'date': date,
                'broker_name': '[SUMMARY]',
                'account_id': 'TOTAL_CASH',
                'stock_code': '',
                'raw_description': f'Total Cash across {len(results)} brokers',
                'holding': 0,
                'broker_price': None,
                'broker_price_currency': 'USD',
                'final_price': None,
                'final_price_source': '',
                'optimized_price_currency': 'USD',
                'multiplier': 1.0,
                'position_value_usd': round(total_cash, 2)
            },
            {
                'date': date,
                'broker_name': '[SUMMARY]',
                'account_id': 'TOTAL_POSITIONS',
                'stock_code': '',
                'raw_description': f'Total Positions (deduplicated across brokers)',
                'holding': 0,
                'broker_price': None,
                'broker_price_currency': 'USD',
                'final_price': None,
                'final_price_source': '',
                'optimized_price_currency': 'USD',
                'multiplier': 1.0,
                'position_value_usd': round(total_positions, 2)
            },
            {
                'date': date,
                'broker_name': '[SUMMARY]',
                'account_id': 'GRAND_TOTAL',
                'stock_code': '',
                'raw_description': f'Grand Total (Cash + Positions)',
                'holding': 0,
                'broker_price': None,
                'broker_price_currency': 'USD',
                'final_price': None,
                'final_price_source': '',
                'optimized_price_currency': 'USD',
                'multiplier': 1.0,
                'position_value_usd': round(grand_total, 2)
            }
        ])
        
        # Combine detail rows and summary rows
        csv_with_summary = pd.concat([csv_df, summary_rows], ignore_index=True)
        csv_with_summary.to_csv(csv_file, index=False, encoding='utf-8')
        logger.info(f"💾 CSV report exported: {csv_file}")
        
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
                'positions': positions_file.name,
                'portfolio_csv': csv_file.name
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
            'portfolio_csv': str(csv_file),
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
                          output_dir: str = None) -> Dict[str, str]:
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
    if output_dir is None:
        output_dir = settings.result_dir
    persistence = DataPersistence(output_dir)
    return persistence.save_broker_data(results, date, exchange_rates) 
