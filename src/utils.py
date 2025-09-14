"""
Utility functions for FundMate broker statement processor.
Contains logging setup, file operations, printing helpers, and validation functions.
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
from image_processor import ProcessedResult


def setup_logging(log_dir: str, date: str) -> None:
    """
    Setup logging configuration with date-based directory structure.
    
    Args:
        log_dir: Base log directory path
        date: Date string in YYYY-MM-DD format for log folder
    """
    log_path = Path(log_dir) / date
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Remove default logger
    logger.remove()
    
    # Add console handler with simplified format for INFO, detailed for ERROR
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
        filter=lambda record: record["level"].name in ["DEBUG", "INFO", "SUCCESS", "WARNING"]
    )
    
    # Add console handler for ERROR with simplified format
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="ERROR"
    )
    
    # Add file handler for all logs with simplified format
    logger.add(
        log_path / "fundmate.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip"
    )
    
    # Add separate error log file with simplified format
    logger.add(
        log_path / "errors.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="ERROR",
        rotation="5 MB",
        retention="30 days",
        compression="zip"
    )
    
    logger.info(f"Logging initialized for date: {date}")
    logger.info(f"Log files saved to: {log_path}")


def validate_date_format(date: str) -> bool:
    """
    Validate date string format (YYYY-MM-DD).
    
    Args:
        date: Date string to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
    return bool(re.match(date_pattern, date))


def check_images_exist(dated_output_folder: str, broker: Optional[str] = None) -> Dict[str, bool]:
    """
    Check which brokers already have converted images.
    
    Args:
        dated_output_folder: Output folder with date subfolder
        broker: Specific broker to check, or None for all
        
    Returns:
        Dict[str, bool]: Dictionary mapping broker names to existence status
    """
    output_path = Path(dated_output_folder)
    existing_images = {}
    
    if not output_path.exists():
        return {}
    
    # Check each broker subdirectory
    for subdir in output_path.iterdir():
        if not subdir.is_dir():
            continue
            
        broker_name = subdir.name
        
        # Filter by specific broker if provided
        if broker and broker_name.upper() != broker.upper():
            continue
        
        # Check for any image files
        image_files = list(subdir.glob("*.png")) + list(subdir.glob("*.jpg"))
        existing_images[broker_name] = len(image_files) > 0
    
    return existing_images


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
            cash_details = []
            if cash_data.get('CNY') is not None:
                cash_details.append(f"CNY: {cash_data['CNY']:,.2f}")
            if cash_data.get('HKD') is not None:
                cash_details.append(f"HKD: {cash_data['HKD']:,.2f}")
            if cash_data.get('USD') is not None:
                cash_details.append(f"USD: {cash_data['USD']:,.2f}")
            if cash_details:
                summary_lines.append(f"      Cash Details: {', '.join(cash_details)}")
        
        # Display position summary
        if result.position_values:
            pv = result.position_values
            successful = pv.get('successful_prices', 0)
            failed = pv.get('failed_prices', 0) 
            total_stocks = successful + failed
            summary_lines.append(f"      Position Details: {successful}/{total_stocks} stocks priced")
            
            if failed > 0:
                summary_lines.append(f"      ⚠️  {failed} stocks failed to get price")
    
    summary_lines.append("\n" + "-" * 80)
    summary_lines.append(f"[TOTAL] Total Cash: ${total_cash_usd:,.2f} USD")
    summary_lines.append(f"[TOTAL] Total Positions: ${total_positions_usd:,.2f} USD")
    summary_lines.append(f"[TOTAL] Grand Total: ${total_cash_usd + total_positions_usd:,.2f} USD")
    summary_lines.append("=" * 80)
    
    # Log the entire summary as one message
    summary_text = "\n".join(summary_lines)
    logger.info(f"Asset Summary Report:\n{summary_text}")
    
    # Also print to console for immediate visibility
    print(summary_text)


def print_cash_summary(results: List[ProcessedResult]) -> None:
    """
    Legacy function - calls new print_asset_summary for backward compatibility.
    """
    print_asset_summary(results)


def print_processing_info(broker_folder: str, date: str, broker: Optional[str], 
                         output: str, force: bool) -> None:
    """
    Print processing information banner.
    
    Args:
        broker_folder: Path to broker statements folder
        date: Processing date
        broker: Specific broker name or None for all
        output: Output directory path
        force: Whether force re-conversion is enabled
    """
    info_lines = [
        "=" * 60,
        "FundMate - Broker Statement Processor",
        "=" * 60,
        f"PDF Folder: {broker_folder}",
        f"Date: {date}",
        f"Broker: {broker or 'All brokers'}",
        f"Output: {output}",
        f"Force Re-conversion: {'Yes' if force else 'No'}",
        "=" * 60
    ]
    
    # Print to console for immediate visibility
    for line in info_lines:
        print(line)


def validate_broker_folder(broker_folder: str) -> bool:
    """
    Validate that the broker folder exists.
    
    Args:
        broker_folder: Path to validate
        
    Returns:
        bool: True if folder exists, False otherwise
    """
    return os.path.exists(broker_folder) 