"""
FundMate - Broker Statement Processor
Main entry point with command-line interface for processing broker statements.
"""

import sys
import argparse
from pathlib import Path
from loguru import logger

from src.broker_processor import BrokerStatementProcessor
from src.data_persistence import save_processing_results
from src.utils import validate_broker_folder, print_processing_info, ensure_output_directories
from src.config import settings
from src.trade_confirmation_processor import (
    TradeConfirmationProcessor, 
    auto_detect_latest_base_date
)


def infer_base_date_from_broker_folder(broker_folder: str, target_date: str) -> str:
    """
    Infer base_date from broker_folder path.
    
    Supports two modes:
    1. Statement mode: Extract date from folder name (e.g., data/20250718_Statement → 2025-07-18)
    2. Archive mode: Scan files for dates and find latest date < target_date
    
    Args:
        broker_folder: Path to broker folder
        target_date: Target date in YYYY-MM-DD format
        
    Returns:
        Inferred base_date in YYYY-MM-DD format
        
    Raises:
        ValueError: If base_date cannot be inferred
    """
    import re
    from datetime import datetime
    
    broker_path = Path(broker_folder)
    
    # Statement mode: Extract date from folder name (e.g., 20250718_Statement)
    match = re.search(r'(\d{8})_Statement', broker_folder)
    if match:
        date_str = match.group(1)  # 20250718
        base_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        logger.info(f"Base date inferred from folder name: {base_date}")
        return base_date
    
    # Archive mode: Scan files for dates (format: BROKER_YYYY-MM-DD_ID.ext)
    if 'archives' in broker_path.parts:
        logger.info("Archive mode detected, scanning for latest base_date...")
        date_pattern = re.compile(r'_(\d{4}-\d{2}-\d{2})_')
        found_dates = set()
        
        for file in broker_path.rglob('*'):
            if file.is_file():
                match = date_pattern.search(file.name)
                if match:
                    found_dates.add(match.group(1))
        
        if not found_dates:
            raise ValueError(f"No dated files found in {broker_folder}")
        
        # Find latest date < target_date
        target_dt = datetime.strptime(target_date, '%Y-%m-%d')
        valid_dates = [d for d in found_dates 
                      if datetime.strptime(d, '%Y-%m-%d') < target_dt]
        
        if not valid_dates:
            raise ValueError(
                f"No base_date found before {target_date}. "
                f"Found dates: {sorted(found_dates)}"
            )
        
        base_date = max(valid_dates)
        logger.info(f"Base date inferred from archive files: {base_date} (from {len(valid_dates)} candidates)")
        return base_date
    
    raise ValueError(
        f"Cannot infer base_date from broker_folder: {broker_folder}\n"
        f"Expected patterns:\n"
        f"  - data/YYYYMMDD_Statement (e.g., data/20250718_Statement)\n"
        f"  - data/archives/ (with files matching BROKER_YYYY-MM-DD_ID.ext)"
    )


def create_argument_parser() -> argparse.ArgumentParser:
    """
    Create and configure the command-line argument parser.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description="FundMate - Process broker statements and extract financial data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  
  python main.py /path/to/statements --broker SDICS --date 2025-02-28
  python main.py /path/to/statements -f  # Force re-conversion
        """
    )
    
    # Required argument
    parser.add_argument(
        'broker_folder',
        type=str,
        help='Path to the folder containing broker PDF statements'
    )
    
    # Optional arguments
    parser.add_argument(
        '--date',
        type=str,
        required=True,
        help='Date for processing in YYYY-MM-DD format (required)'
    )
    
    parser.add_argument(
        '--broker',
        type=str,
        default=None,
        help='Specific broker to process (e.g., SDICS, HUATAI, IB). If not specified, all brokers will be processed.'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output folder for converted images (default: ./out/pictures)'
    )
    
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Force re-conversion of PDFs even if images already exist'
    )
    
    parser.add_argument(
        '--max-workers',
        type=int,
        default=10,
        help='Maximum number of concurrent threads for broker processing (default: 10)'
    )
    
    # Trade Confirmation mode arguments
    parser.add_argument(
        '--use-tc',
        action='store_true',
        help='Use trade confirmation mode for incremental portfolio update'
    )
    
    parser.add_argument(
        '--base-date',
        type=str,
        default=None,
        help='Base date for trade confirmation mode (YYYY-MM-DD). Auto-detect if not specified.'
    )
    
    parser.add_argument(
        '--tc-folder',
        type=str,
        default='data/archives/TradeConfirmation',
        help='Trade confirmation folder path (default: data/archives/TradeConfirmation)'
    )
    
    return parser


def main():
    """
    Main entry point for the FundMate broker statement processor.
    Handles command-line arguments and orchestrates the processing workflow.
    """
    # Parse command-line arguments
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Setup configuration and ensure directories
    if args.output is None:
        args.output = settings.pictures_dir
    settings.ensure_directories()
    
    # Check if using Trade Confirmation mode
    if args.use_tc:
        # Initialize logging to target date (not base date)
        from utils import setup_logging
        setup_logging(settings.LOG_DIR, args.date)
        
        logger.info("=" * 60)
        logger.info("Trade Confirmation Mode (End-to-End)")
        logger.info("=" * 60)
        
        # Auto-infer base_date from broker_folder if not provided
        if args.base_date is None:
            try:
                args.base_date = infer_base_date_from_broker_folder(
                    args.broker_folder, 
                    args.date
                )
            except ValueError as e:
                logger.error(str(e))
                sys.exit(1)
        
        logger.info(f"Broker Folder: {args.broker_folder}")
        logger.info(f"Base Date: {args.base_date}")
        logger.info(f"Target Date: {args.date}")
        logger.info(f"TC Folder: {args.tc_folder}")
        
        # Process with trade confirmations (end-to-end mode)
        try:
            tc_processor = TradeConfirmationProcessor()
            processed_results, exchange_rates, date = tc_processor.process_with_trade_confirmation(
                base_broker_folder=args.broker_folder,
                base_date=args.base_date,
                target_date=args.date,
                tc_folder=args.tc_folder
            )
        except Exception as e:
            logger.error(f"Trade confirmation processing failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    else:
        # Normal mode: Process broker statements
        
        # Validate broker folder exists
        if not validate_broker_folder(args.broker_folder):
            print(f"ERROR: PDF folder does not exist: {args.broker_folder}")
            print("Please check the path and try again.")
            sys.exit(1)
        
        # Display processing information
        print_processing_info(
            broker_folder=args.broker_folder,
            date=args.date,
            broker=args.broker,
            output=args.output,
            force=args.force
        )
        
        # Process broker statements
        try:
            processor = BrokerStatementProcessor()
            processed_results, exchange_rates, date = processor.process_folder(
                broker_folder=args.broker_folder,
                image_output_folder=args.output,
                date=args.date,
                broker=args.broker,
                force=args.force,
                max_workers=args.max_workers
            )
        except Exception as e:
            logger.error(f"Broker statement processing failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # Save results to persistent storage (common for both modes)
    if processed_results and exchange_rates and date:
        logger.info("Saving processed data to persistent storage...")
        try:
            # Use configured result directory
            result_output_dir = Path(settings.result_dir)
            
            saved_files = save_processing_results(
                results=processed_results, 
                date=date, 
                exchange_rates=exchange_rates,
                output_dir=str(result_output_dir)
            )
            logger.success(f"Data persistence completed. Files saved: {list(saved_files.keys())}")
        except Exception as e:
            logger.error(f"Failed to save processed data: {e}")
    else:
        logger.warning("No data to save - processing may have failed")


if __name__ == "__main__":
    main()
