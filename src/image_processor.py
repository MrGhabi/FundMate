import os
import time
from pydantic import BaseModel
from typing import Optional, Literal, List, Dict, Any, Union
from prompt_templates import PROMPT_TEMPLATES
import requests
from datetime import datetime
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from llm_handler import LLMHandler
from price_fetcher import PriceFetcher

class ProcessedResult(BaseModel):
    broker_name: str
    account_id: str
    cash_data: Dict[str, Union[float, str, None]]
    positions: List[Dict[str, Union[str, int]]]
    usd_total: float
    # New fields for position valuation
    position_values: Optional[Dict[str, Any]] = None
    total_position_value_usd: float = 0.0



class ImageProcessor:
    def __init__(self):
        self.llm_handler = LLMHandler()
        self.PROMPT_TEMPLATES = PROMPT_TEMPLATES
        self.price_fetcher = PriceFetcher()
    
    def get_exchange_rates(self, date: str = None) -> Dict[str, float]:
        """Get exchange rate data with support for specified date"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Use convert endpoint to get HKD and CNY exchange rates separately
            hkd_url = f"https://api.exchangerate.host/convert?access_key=4803c190bc2db4046a7ec3007224d1b7&from=USD&to=HKD&amount=1&date={date}"
            cny_url = f"https://api.exchangerate.host/convert?access_key=4803c190bc2db4046a7ec3007224d1b7&from=USD&to=CNY&amount=1&date={date}"
            
            logger.info(f"Fetching exchange rate data for {date}...")
            
            # Get HKD exchange rate
            hkd_response = requests.get(hkd_url, timeout=30)
            hkd_response.raise_for_status()
            hkd_data = hkd_response.json()
            
            time.sleep(1)
            # Get CNY exchange rate
            cny_response = requests.get(cny_url, timeout=30)
            cny_response.raise_for_status()
            cny_data = cny_response.json()
            
            # Check if API response is successful
            if hkd_data.get('success') and cny_data.get('success'):
                hkd_rate = hkd_data.get('result', 7.8)
                cny_rate = cny_data.get('result', 7.2)
                
                logger.info(f"Exchange rate data retrieved successfully: CNY={cny_rate}, HKD={hkd_rate}")
                
                return {
                    'CNY': cny_rate,
                    'HKD': hkd_rate,
                    'USD': 1.0
                }
            else:
                error_msg = []
                if not hkd_data.get('success'):
                    error_msg.append(f"HKD: {hkd_data.get('error', 'Unknown error')}")
                if not cny_data.get('success'):
                    error_msg.append(f"CNY: {cny_data.get('error', 'Unknown error')}")
                raise ValueError(f"API request failed: {', '.join(error_msg)}")
                
        except Exception as e:
            logger.error(f"Failed to get historical exchange rates for {date}, using default rates: {e}")
            return {
                'CNY': 7.2,
                'HKD': 7.8,
                'USD': 1.0
            }
    
    def convert_to_usd(self, amount: float, currency: str, exchange_rates: Dict[str, float]) -> float:
        """Convert specified currency amount to USD"""
        if currency == 'USD':
            return amount
        rate = exchange_rates.get(currency, 1.0)
        return amount / rate
    

    
    def get_all_png_images(self, folder_path: str) -> List[str]:
        if not os.path.exists(folder_path):
            raise ValueError(f"Folder does not exist: {folder_path}")
        
        image_paths = sorted([
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".png")
        ])
        
        if not image_paths:
            raise ValueError(f"No PNG images found in folder: {folder_path}")
        
        return image_paths
    
    def process_images(self, prompt: List[Dict[str, Any]], image_folder: str) -> Dict[str, Any]:
        image_paths = self.get_all_png_images(image_folder)
        return self.llm_handler.process_images_with_prompt(prompt, image_paths)
    

    def process_broker_data(self, prompt: List[Dict[str, Any]], image_folder: str, broker_name: str, account_id: str, exchange_rates: Dict[str, float], date: str = None) -> ProcessedResult:
        """
        Process broker images and return both console output and structured data for summary.
        Single API call replaces both process_and_print and process_for_summary.
        
        Args:
            prompt: Prompt template for this broker
            image_folder: Path to broker's image folder
            broker_name: Name of the broker
            account_id: Account identifier for this broker
            exchange_rates: Currency exchange rates
            
        Returns:
            ProcessedResult: Structured data for summary
            
        Raises:
            Exception: If processing fails
        """
        try:
            # Single API call to get all data
            data = self.process_images(prompt, image_folder)
            
            # Parse cash data
            cash_data = data['Cash']
            CNY = float(cash_data['CNY'].replace(",", "")) if cash_data.get('CNY') else None
            HKD = float(cash_data['HKD'].replace(",", "")) if cash_data.get('HKD') else None
            USD = float(cash_data['USD'].replace(",", "")) if cash_data.get('USD') else None
            Total = float(cash_data['Total'].replace(",", "")) if cash_data.get('Total') else None
            Total_type = cash_data.get('Total_type')
            
            positions = data['Positions']
            
            # Log extraction results (replaces process_and_print functionality)
            log_content = []
            display_name = f"{broker_name}/{account_id}" if account_id != 'DEFAULT' else broker_name
            log_content.append(f"{display_name} Broker Statement Extraction Result:")
            log_content.append("Cash Section:")
            log_content.append(f"  CNY: {CNY}")
            log_content.append(f"  HKD: {HKD}")
            log_content.append(f"  USD: {USD}")
            log_content.append(f"  Total: {Total}")
            log_content.append(f"  Total_type: {Total_type}")
            log_content.append("Positions Section:")
            if len(positions) == 0:
                log_content.append('No positions')
            else:
                for pos in positions:
                    Holding = int(float(pos['Holding'].replace(",", "")))
                    log_content.append(f"  {pos['StockCode']}: {Holding}")
            
            # Output all content as a single log entry
            logger.info("\n".join(log_content))
            
            # Calculate USD total for summary
            usd_total = 0.0
            if Total is not None and Total_type is not None:
                # If Total value exists, convert directly to USD
                usd_total = self.convert_to_usd(Total, Total_type, exchange_rates)
            else:
                # If Total value does not exist, convert each currency and sum
                if CNY is not None:
                    usd_total += self.convert_to_usd(CNY, 'CNY', exchange_rates)
                if HKD is not None:
                    usd_total += self.convert_to_usd(HKD, 'HKD', exchange_rates)
                if USD is not None:
                    usd_total += USD
            
            # Build cash data dictionary
            cash_dict = {
                'CNY': CNY,
                'HKD': HKD,
                'USD': USD,
                'Total': Total,
                'Total_type': Total_type
            }
            
            # Build positions data list
            positions_list = []
            for pos in positions:
                positions_list.append({
                    'StockCode': pos['StockCode'],
                    'Holding': int(float(pos['Holding'].replace(",", "")))
                })
            
            # Calculate position values if date is provided and positions exist
            position_values = None
            total_position_value_usd = 0.0
            
            if date and positions_list:
                try:
                    logger.info(f"Calculating position values for {broker_name}/{account_id} on {date}")
                    position_values = self.price_fetcher.calculate_position_values(positions_list, date)
                    total_position_value_usd = position_values.get('total_value_usd', 0.0)
                    
                    logger.info(f"Position valuation: ${total_position_value_usd:,.2f} USD "
                              f"({position_values.get('successful_prices', 0)}/{len(positions_list)} stocks priced)")
                except Exception as e:
                    logger.warning(f"Position valuation failed for {broker_name}: {e}")
                    position_values = None
                    total_position_value_usd = 0.0
            
            return ProcessedResult(
                broker_name=broker_name,
                account_id=account_id,
                cash_data=cash_dict,
                positions=positions_list,
                usd_total=usd_total,
                position_values=position_values,
                total_position_value_usd=total_position_value_usd
            )
            
        except Exception as e:
            logger.error(f"Failed to process {broker_name}: {e}")
            raise

    def process_brokers_concurrent(self, broker_data_list: List[Dict], exchange_rates: Dict[str, float], 
                                 max_workers: int = 3, date: str = None) -> List[ProcessedResult]:
        """
        Process multiple brokers concurrently using thread pool.
        
        Args:
            broker_data_list: List of broker data dictionaries containing broker_name, prompt, image_folder
            exchange_rates: Currency exchange rates
            max_workers: Maximum number of concurrent threads
            
        Returns:
            List[ProcessedResult]: Results from successfully processed brokers
        """
        results = []
        total_brokers = len(broker_data_list)
        
        logger.info(f"Starting concurrent processing of {total_brokers} brokers (max_workers={max_workers})")
        
        def process_single_broker(broker_data: Dict) -> ProcessedResult:
            """
            Process a single broker's data.
            
            Args:
                broker_data: Dictionary containing broker information
                
            Returns:
                ProcessedResult: Processed broker data
                
            Raises:
                Exception: If processing fails
            """
            broker_name = broker_data['broker_name']
            account_id = broker_data.get('account_id', 'DEFAULT')
            prompt = broker_data['prompt']
            image_folder = broker_data['image_folder']
            
            display_name = f"{broker_name}/{account_id}" if account_id != 'DEFAULT' else broker_name
            logger.info(f"Processing {display_name} broker data...")
            result = self.process_broker_data(prompt, image_folder, broker_name, account_id, exchange_rates, date)
            logger.success(f"{display_name} data processing completed")
            return result
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all broker processing tasks
            future_to_broker = {
                executor.submit(process_single_broker, broker_data): broker_data['broker_name']
                for broker_data in broker_data_list
            }
            
            # Process completed tasks as they finish
            completed_count = 0
            failed_count = 0
            
            for future in as_completed(future_to_broker):
                broker_name = future_to_broker[future]
                completed_count += 1
                
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)
                        logger.info(f"Progress: {completed_count}/{total_brokers} brokers completed")
                    else:
                        failed_count += 1
                        logger.warning(f"Broker {broker_name} returned None result")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Broker {broker_name} failed during concurrent processing: {e}")
        
        logger.info(f"Concurrent processing completed: {len(results)} successful, {failed_count} failed")
        return results


if __name__ == "__main__":
    processor = ImageProcessor()

    broker_name = "TIGER"
    
    image_folder = "../pictures/" + broker_name
    prompt = processor.PROMPT_TEMPLATES[broker_name]
    
    processor.process_and_print(prompt, image_folder, broker_name)