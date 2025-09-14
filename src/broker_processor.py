"""
Core broker statement processor module.
Contains the main business logic for processing broker statements and orchestrating the workflow.
"""

from pathlib import Path
from typing import List, Tuple, Optional
from loguru import logger

from pdf_converter import convert_pdf_directory
from image_processor import ImageProcessor, ProcessedResult
from excel_parser import ExcelPositionParser
from utils import setup_logging, validate_date_format, check_images_exist, print_asset_summary


class BrokerStatementProcessor:
    """
    Core processor for broker statement data extraction and processing.
    Orchestrates PDF conversion, image processing, and data extraction workflow.
    """
    
    def __init__(self):
        """Initialize the processor with image and excel processor instances."""
        self.image_processor = ImageProcessor()
        self.excel_parser = ExcelPositionParser()
    
    def process_folder(self, broker_folder: str, image_output_folder: str, 
                      date: str = None, broker: str = None, force: bool = False, 
                      max_workers: int = 3) -> Tuple[Optional[List], Optional[dict], Optional[str]]:
        """
        Process broker folder with complete workflow:
        1. Validate date format
        2. Setup logging
        3. Check existing images
        4. Convert PDFs to images
        5. Get exchange rates
        6. Process images and extract data
        7. Generate summary report
        
        Args:
            broker_folder: Path to folder containing broker PDF statements
            image_output_folder: Output folder for converted images
            date: Date string in YYYY-MM-DD format
            broker: Specific broker to process, or None for all
            force: Force re-conversion of PDFs even if images exist
            max_workers: Maximum number of concurrent threads
            
        Returns:
            Tuple: (processed_results, exchange_rates, date) or (None, None, None) if processing fails
        """
        # Step 1: Validate date format
        if date is None or not validate_date_format(date):
            print(f"ERROR: Invalid date format: {date}. Expected YYYY-MM-DD")
            return None, None, None
        
        # Step 2: Setup logging
        setup_logging("./log", date)
        
        # Step 3: Log processing start
        logger.info(f"Starting folder processing: {broker_folder}")
        if broker:
            logger.info(f"Processing specific broker: {broker}")
        logger.info(f"Using date: {date}")
        
        # Step 4: Create dated output directory
        dated_output_folder = str(Path(image_output_folder) / date)
        logger.info(f"Output directory: {dated_output_folder}")
        
        # Step 5: Check existing images if not forcing
        if not force:
            existing_images = check_images_exist(dated_output_folder, broker)
            if existing_images:
                logger.info("Checking existing images...")
                for broker_name, exists in existing_images.items():
                    if exists:
                        logger.warning(f"{broker_name} - Images already exist (use -f to force re-conversion)")
        
        # Step 6: Convert PDFs to images
        logger.info("Converting PDFs to images...")
        try:
            convert_pdf_directory(broker_folder, dated_output_folder, broker_filter=broker, force=force)
            logger.success("PDF conversion completed")
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return None, None, None
        
        # Step 7: Get exchange rates
        logger.info("Fetching exchange rate data...")
        try:
            exchange_rates = self.image_processor.get_exchange_rates(date)
            logger.success(f"Exchange rates retrieved: CNY={exchange_rates['CNY']}, HKD={exchange_rates['HKD']}")
        except Exception as e:
            logger.error(f"Failed to fetch exchange rates: {e}")
            return None, None, None
        
        # Step 8: Process image data
        logger.info("Processing image data...")
        image_root = Path(dated_output_folder)
        
        if not image_root.exists():
            logger.error(f"Image output folder does not exist: {dated_output_folder}")
            return None, None, None
        
        # Step 9: Prepare broker data for processing
        broker_data_list = self._prepare_broker_data(image_root, broker)
        
        # Step 10: Process PDF images using concurrent processing
        if broker_data_list:
            logger.info(f"Found {len(broker_data_list)} brokers to process")
            pdf_results = self.image_processor.process_brokers_concurrent(
                broker_data_list, exchange_rates, max_workers, date
            )
        else:
            logger.warning("No PDF brokers found to process")
            pdf_results = []
        
        # Step 11: Process Excel data from dated broker folder
        logger.info("Processing Excel data...")
        dated_broker_folder = str(Path(broker_folder) / date)
        excel_results = self._process_excel_data(dated_broker_folder, date, exchange_rates)
        
        # Step 12: Merge PDF and Excel results
        merged_results = self._merge_position_data(pdf_results, excel_results)
        
        # Step 13: Generate complete asset summary
        if merged_results:
            print_asset_summary(merged_results)
        
        logger.info("All data processing completed!")
        
        # Return results for persistence
        return merged_results, exchange_rates, date
    
    def _prepare_broker_data(self, image_root: Path, broker_filter: Optional[str] = None) -> List[dict]:
        """
        Prepare broker data list for concurrent processing.
        Now supports both single-account brokers and multi-account brokers with sub-directories.
        
        Args:
            image_root: Root directory containing broker image folders
            broker_filter: Specific broker to filter, or None for all
            
        Returns:
            List[dict]: List of broker data dictionaries ready for processing
        """
        broker_data_list = []
        
        for subdir in image_root.iterdir():
            if not subdir.is_dir():
                continue
                
            broker_name = subdir.name
            
            # Filter by broker if specified
            if broker_filter and broker_name.upper() != broker_filter.upper():
                continue
            
            # Check for corresponding prompt template
            if broker_name not in self.image_processor.PROMPT_TEMPLATES:
                logger.warning(f"Skipping {broker_name} (no prompt template found)")
                continue
            
            # Check for direct image files (legacy/single-account structure)
            direct_image_files = list(subdir.glob("*.png")) + list(subdir.glob("*.jpg"))
            
            if direct_image_files:
                # Legacy structure: images are directly in broker folder
                logger.info(f"Processing {broker_name} with legacy structure (direct images)")
                broker_data = {
                    'broker_name': broker_name,
                    'account_id': 'DEFAULT',
                    'prompt': self.image_processor.PROMPT_TEMPLATES[broker_name],
                    'image_folder': str(subdir)
                }
                broker_data_list.append(broker_data)
            else:
                # New structure: check for account subdirectories
                account_folders = [d for d in subdir.iterdir() if d.is_dir()]
                
                if not account_folders:
                    logger.warning(f"Skipping {broker_name} (no images or account folders found)")
                    continue
                
                logger.info(f"Processing {broker_name} with multi-account structure ({len(account_folders)} accounts)")
                
                # Process each account folder
                for account_folder in account_folders:
                    account_id = account_folder.name
                    
                    # Check for images in account folder
                    account_image_files = list(account_folder.glob("*.png")) + list(account_folder.glob("*.jpg"))
                    
                    if not account_image_files:
                        logger.warning(f"Skipping {broker_name}/{account_id} (no images found)")
                        continue
                    
                    # Prepare account data for processing
                    broker_data = {
                        'broker_name': broker_name,
                        'account_id': account_id,
                        'prompt': self.image_processor.PROMPT_TEMPLATES[broker_name],
                        'image_folder': str(account_folder)
                    }
                    broker_data_list.append(broker_data)
                    logger.info(f"Added processing task for {broker_name}/{account_id}")
        
        return broker_data_list
    
    def _process_excel_data(self, broker_folder: str, date: str, exchange_rates: dict) -> List[ProcessedResult]:
        """
        Process Excel position data from broker folder.
        
        Args:
            broker_folder: Path to broker folder containing Excel files
            date: Processing date
            exchange_rates: Exchange rate data
            
        Returns:
            List of ProcessedResult objects with Excel position data
        """
        try:
            # Parse Excel data using ExcelPositionParser
            excel_data = self.excel_parser.parse_directory(broker_folder)
            
            if not excel_data:
                logger.info("No Excel data found in broker folder")
                return []
            
            results = []
            
            # Convert Excel data to ProcessedResult format
            for broker_name, positions in excel_data.items():
                logger.info(f"Processing {len(positions)} Excel positions for {broker_name}")
                
                # Create ProcessedResult for Excel data
                # Note: Excel data typically doesn't contain cash, only positions
                excel_result = ProcessedResult(
                    broker_name=broker_name,
                    account_id='EXCEL',  # Mark as Excel source
                    cash_data={'Total': 0.0, 'Total_type': 'USD'},  # No cash in Excel
                    positions=positions,
                    usd_total=0.0  # No cash
                )
                
                # Calculate position values using PriceFetcher
                position_values = self.image_processor.price_fetcher.calculate_position_values(
                    positions, date
                )
                excel_result.position_values = position_values
                excel_result.total_position_value_usd = position_values.get('total_value_usd', 0.0)
                
                results.append(excel_result)
                logger.success(f"Excel data processed for {broker_name}: {len(positions)} positions, ${excel_result.total_position_value_usd:,.2f} total value")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to process Excel data: {e}")
            return []
    
    def _merge_position_data(self, pdf_results: List[ProcessedResult], 
                           excel_results: List[ProcessedResult]) -> List[ProcessedResult]:
        """
        Merge PDF and Excel position data.
        
        Strategy: Keep all PDF results as-is (they contain cash data).
        Add Excel results as separate brokers to avoid conflicts.
        
        Args:
            pdf_results: Results from PDF processing
            excel_results: Results from Excel processing
            
        Returns:
            Merged list of ProcessedResult objects
        """
        merged = []
        
        # Add all PDF results
        if pdf_results:
            merged.extend(pdf_results)
            logger.info(f"Added {len(pdf_results)} PDF broker results")
        
        # Add all Excel results
        if excel_results:
            merged.extend(excel_results)
            logger.info(f"Added {len(excel_results)} Excel broker results")
        
        logger.success(f"Data merge completed: {len(merged)} total broker accounts")
        return merged 