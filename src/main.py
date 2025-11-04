"""
FundMate - Broker Statement Processor
Main entry point with command-line interface for processing broker statements.
"""

import sys
import argparse
from pathlib import Path
from loguru import logger

try:
    from .broker_processor import BrokerStatementProcessor
    from .data_persistence import save_processing_results
    from .utils import validate_broker_folder, print_processing_info, ensure_output_directories
    from .config import settings
except (ImportError, ValueError):
    from broker_processor import BrokerStatementProcessor
    from data_persistence import save_processing_results
    from utils import validate_broker_folder, print_processing_info, ensure_output_directories
    from config import settings


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
    
    return parser


def main():
    """
    Main entry point for the FundMate broker statement processor.
    Handles command-line arguments and orchestrates the processing workflow.
    """
    # Parse command-line arguments
    parser = create_argument_parser()
    args = parser.parse_args()
    
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
    
    # Setup configuration and ensure directories
    if args.output is None:
        args.output = settings.pictures_dir
    settings.ensure_directories()
    
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
        
        # Save results to persistent storage
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
            
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        logger.error("Please check your configuration and try again.")
        sys.exit(1)
    finally:
        # Clean shutdown
        logger.info("Shutting down gracefully...")
        # Remove all loguru handlers to prevent hanging
        logger.remove()


if __name__ == "__main__":
    main()
