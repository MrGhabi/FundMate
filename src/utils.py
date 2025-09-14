"""
Utility functions for FundMate broker statement processor.
Contains helper functions for validation, logging, and display formatting.
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Union
from loguru import logger

from image_processor import ProcessedResult


def setup_logging(log_dir: str, date: str) -> None:
    """
    Setup logging configuration with date-specific log files.
    
    Args:
        log_dir: Directory for log files
        date: Date string for log organization
    """
    log_path = Path(log_dir) / date
    log_path.mkdir(parents=True, exist_ok=True)
    
    log_file = log_path / "fundmate.log"
    
    # Remove default handler and add both console and file handlers
    logger.remove()
    
    # Add console handler
    logger.add(
        lambda msg: print(msg, end=""),
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}\n",
        colorize=False
    )
    
    # Add file handler
    logger.add(
        str(log_file),
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        backtrace=True,
        diagnose=True
    )
    
    logger.info(f"Logging initialized for date: {date}")
    logger.info(f"Log files saved to: {log_path}")


def validate_date_format(date_str: str) -> bool:
    """
    Validate date string format (YYYY-MM-DD).
    
    Args:
        date_str: Date string to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    if not date_str:
        return False
    
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def validate_broker_folder(folder_path: str) -> bool:
    """
    Validate that broker folder exists.
    
    Args:
        folder_path: Path to broker folder
        
    Returns:
        bool: True if folder exists, False otherwise
    """
    return os.path.exists(folder_path) and os.path.isdir(folder_path)


def print_processing_info(broker_folder: str, date: str, broker: str = None, 
                         output: str = None, force: bool = False) -> None:
    """
    Print processing information banner.
    
    Args:
        broker_folder: Path to broker folder
        date: Processing date
        broker: Specific broker filter (if any)
        output: Output directory
        force: Force re-conversion flag
    """
    print("=" * 60)
    print("FundMate - Broker Statement Processor")
    print("=" * 60)
    print(f"PDF Folder: {broker_folder}")
    print(f"Date: {date}")
    print(f"Broker: {broker if broker else 'All brokers'}")
    print(f"Output: {output}")
    print(f"Force Re-conversion: {'Yes' if force else 'No'}")
    print("=" * 60)
    print()


def check_images_exist(output_folder: str, broker_filter: str = None) -> Dict[str, bool]:
    """
    Check if images already exist for brokers.
    
    Args:
        output_folder: Output directory for images
        broker_filter: Specific broker to check (optional)
        
    Returns:
        Dict[str, bool]: Mapping of broker names to existence status
    """
    output_path = Path(output_folder)
    existing_images = {}
    
    if not output_path.exists():
        # Create output directory if it doesn't exist
        output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created output directory: {output_folder}")
        return {}
    
    for broker_dir in output_path.iterdir():
        if not broker_dir.is_dir():
            continue
            
        broker_name = broker_dir.name
        
        # Filter by broker if specified
        if broker_filter and broker_name.upper() != broker_filter.upper():
            continue
            
        # Check for image files in broker directory
        image_files = list(broker_dir.glob("*.png")) + list(broker_dir.glob("*.jpg"))
        existing_images[broker_name] = len(image_files) > 0
    
    return existing_images


def ensure_output_directories() -> None:
    """
    Ensure all required output directories exist.
    Creates the standard FundMate output directory structure.
    """
    directories = [
        Path("./out"),
        Path("./out/pictures"),
        Path("./out/result"),
        Path("./log")
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {directory}")


def print_asset_summary(results: List[ProcessedResult]) -> None:
    """
    Print complete asset summary (cash + positions) for all processed brokers.
    
    Args:
        results: List of ProcessedResult objects from broker processing
    """
    summary_lines = []
    summary_lines.append("=" * 80)
    summary_lines.append("Complete Asset Summary (USD)")
    summary_lines.append("=" * 80)
    
    # First, show list of all brokers for easy reference
    summary_lines.append("\n📊 BROKERS PROCESSED:")
    broker_list = []
    for result in results:
        display_name = f"{result.broker_name}/{result.account_id}" if result.account_id != 'DEFAULT' else result.broker_name
        source_type = "📊 Excel" if result.account_id == 'EXCEL' else "📄 PDF"
        broker_list.append(f"   {source_type} {display_name}")
    
    summary_lines.extend(broker_list)
    summary_lines.append(f"   Total: {len(results)} accounts")
    summary_lines.append("\n" + "-" * 80)
    
    total_cash_usd = 0.0
    total_positions_usd = 0.0
    
    for result in results:
        broker_name = result.broker_name
        account_id = result.account_id
        cash_usd = result.usd_total
        position_usd = result.total_position_value_usd
        cash_data = result.cash_data
        
        total_cash_usd += cash_usd
        total_positions_usd += position_usd
        
        # Create display name
        display_name = f"{broker_name}/{account_id}" if account_id != 'DEFAULT' else broker_name
        
        summary_lines.append(f"\n[BROKER] {display_name}:")
        summary_lines.append(f"   💰 Cash Total: ${cash_usd:,.2f}")
        summary_lines.append(f"   📈 Position Total: ${position_usd:,.2f}")
        summary_lines.append(f"   🏦 Account Total: ${cash_usd + position_usd:,.2f}")
        
        # Display original currency information
        if cash_data.get('Total') is not None:
            total_type = cash_data.get('Total_type', 'USD')
            summary_lines.append(f"      Original Cash: {cash_data['Total']:,} {total_type}")
        else:
            # Show individual currency details
            cash_details = []
            if cash_data.get('CNY') is not None:
                cash_details.append(f"CNY: {cash_data['CNY']:,.2f}")
            if cash_data.get('HKD') is not None:
                cash_details.append(f"HKD: {cash_data['HKD']:,.2f}")
            if cash_data.get('USD') is not None:
                cash_details.append(f"USD: {cash_data['USD']:,.2f}")
            if cash_details:
                summary_lines.append(f"      Cash Details: {', '.join(cash_details)}")
        
        # Display position information
        if result.position_values:
            pv = result.position_values
            successful = pv.get('successful_prices', 0)
            failed = pv.get('failed_prices', 0)
            total_stocks = successful + failed
            summary_lines.append(f"      Position Details: {successful}/{total_stocks} stocks priced")
            
            if failed > 0:
                summary_lines.append(f"      ⚠️  {failed} stocks failed to get price")
    
    # Add totals
    summary_lines.append("\n" + "-" * 80)
    summary_lines.append(f"[TOTAL] Total Cash: ${total_cash_usd:,.2f} USD")
    summary_lines.append(f"[TOTAL] Total Positions: ${total_positions_usd:,.2f} USD")
    summary_lines.append(f"[TOTAL] Grand Total: ${total_cash_usd + total_positions_usd:,.2f} USD")
    summary_lines.append("=" * 80)
    
    # Print and log the summary
    summary_text = "\n".join(summary_lines)
    logger.info(f"Asset Summary Report:\n{summary_text}")
    print(summary_text)


def print_cash_summary(results: List[ProcessedResult]) -> None:
    """
    Legacy function - calls new print_asset_summary for backward compatibility.
    """
    print_asset_summary(results)