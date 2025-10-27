"""
Utility functions for FundMate broker statement processor.
Contains helper functions for validation, logging, and display formatting.
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Union, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from broker_processor import ProcessedResult


def _identify_hk_option(stock_code: str, raw_description: str = None) -> bool:
    """
    Identify if this is a Hong Kong option based on code pattern.
    
    NOTE: Fallback mechanism (executes when broker doesn't provide multiplier):
    1. TIGER broker provides multiplier → this function is bypassed (Priority 1)
    2. Other brokers without multiplier → this function executes (Priority 4)
    3. Used to determine if we should query Futu API for HK option multiplier
    
    Updated to support modern HKATS formats like "CLI 250929 19.00 CALL".
    """
    if not stock_code and not raw_description:
        return False
    
    # Check for HKATS code pattern: 3 letters + 6 or 8 digits
    # Examples: "CLI 250929 19.00 CALL" or "(CLI.HK 20250929 CALL 19.0)"
    import re
    description = raw_description or stock_code or ""
    if re.search(r'[A-Z]{3}[\s.]+(?:HK\s+)?\d{6,8}', description):
        return True
    
    # Legacy pattern: "XXXX OPTION" (no longer used but kept for compatibility)
    for text in [stock_code, raw_description]:
        if text and text.endswith(" OPTION"):
            underlying_code = text.replace(" OPTION", "").strip()
            # HK stock codes: 4 digits, start with 0-3, 9
            if (len(underlying_code) == 4 and 
                underlying_code.isdigit() and
                underlying_code.startswith(('0', '1', '2', '3', '9'))):
                return True
    
    return False


def is_option_contract(stock_code: str, raw_description: str = None) -> bool:
    """
    Simple option detection - options have obvious names like "CALL", "PUT", "OPTION"
    Also detects OCC format: SYMBOL YYMMDD C/P PRICE (e.g., SBET260116P25000)
    """
    import re
    
    # Check stock code for option keywords
    if stock_code and isinstance(stock_code, str):
        upper_code = stock_code.upper()
        if any(keyword in upper_code for keyword in ['OPTION', 'CALL', 'PUT']):
            return True
        # Also check for single-letter C/P at the end (common in option symbols)
        if upper_code.endswith(' C') or upper_code.endswith(' P'):
            return True
        # Check for OCC format: SYMBOL(1-4 letters) YYMMDD(6 digits) C/P(1 letter) PRICE(digits)
        # Example: SBET260116P25000
        if re.match(r'^[A-Z]{1,4}\d{6}[CP]\d+$', upper_code):
            return True
    
    # Check raw description for option keywords  
    if raw_description and isinstance(raw_description, str):
        upper_desc = raw_description.upper()
        if any(keyword in upper_desc for keyword in ['OPTION', 'CALL', 'PUT']):
            return True
        # Check for OCC format in description
        if re.match(r'^[A-Z]{1,4}\d{6}[CP]\d+$', upper_desc):
            return True
    
    return False


def get_option_multiplier(stock_code: str, raw_description: str = None, broker_multiplier: int = None) -> int:
    """
    Get the correct multiplier for position value calculation
    
    Args:
        stock_code: The stock code/symbol
        raw_description: Optional raw description from broker
        broker_multiplier: Multiplier from broker statement (highest priority)
        
    Returns:
        1 for stocks and OTC options, real multiplier for HK options from Futu API, 
        100 for other standard exchange options
    """
    # Priority 1: Use broker-provided multiplier if available
    if broker_multiplier is not None and broker_multiplier > 0:
        logger.debug(f"Using broker-provided multiplier: {broker_multiplier}")
        return int(broker_multiplier)
    
    # Check if it's an option first
    if not is_option_contract(stock_code, raw_description):
        return 1  # Regular stock
    
    # Check for OTC options FIRST - multiplier is always 1
    if stock_code and isinstance(stock_code, str):
        upper_code = stock_code.upper()
        if 'OTC' in upper_code:
            return 1  # OTC option
    
    if raw_description and isinstance(raw_description, str):
        upper_desc = raw_description.upper()
        if 'OTC' in upper_desc:
            return 1  # OTC option
    
    # Check for HK options (non-OTC)
    if _identify_hk_option(stock_code, raw_description):
        # LIMITATION: Cannot query Futu API for multiplier
        # - Futu API needs stock code (HK.00700), but we only have HKATS code (CLI)
        # - No mapping exists: CLI → stock code
        # - Solution: Use 100 as conservative fallback
        # - RELY ON broker-provided multiplier (Priority 1 above)
        logger.warning(
            f"HK option detected but cannot get multiplier from Futu API: {stock_code or raw_description}. "
            f"HKATS code has no mapping to stock code. Using fallback multiplier=100. "
            f"Recommend broker to provide 'Multiplier' field in statement."
        )
        return 100
    
    # Standard exchange option - multiplier is 100
    return 100


def calculate_position_value(price: float, holding: int, stock_code: str, 
                            raw_description: str = None, broker_multiplier: int = None) -> tuple:
    """
    Unified position value calculation - single source of truth
    
    Args:
        price: Price per share/contract
        holding: Number of shares/contracts
        stock_code: Stock code/symbol
        raw_description: Optional raw description from broker
        broker_multiplier: Optional multiplier from broker statement
    
    Returns:
        Tuple of (position_value, multiplier_used)
    """
    if price is None or price <= 0:
        return (0.0, 1)
    
    multiplier = get_option_multiplier(stock_code, raw_description, broker_multiplier)
    position_value = price * holding * multiplier
    
    if multiplier > 1:
        logger.debug(f"Applied {multiplier}x option multiplier for {stock_code}: "
                    f"{holding} × {price} × {multiplier} = {position_value}")
    else:
        logger.debug(f"Stock/OTC calculation for {stock_code}: "
                    f"{holding} × {price} = {position_value}")
    
    return (position_value, multiplier)


def setup_logging(log_dir: str, date: str) -> None:
    """
    Setup logging configuration with timestamped log files.
    
    Args:
        log_dir: Directory for log files
        date: Date string for log organization
    """
    from datetime import datetime
    
    log_path = Path(log_dir) / date
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Create timestamped log file name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"fundmate_{timestamp}.log"
    
    # Remove default handler and add both console and file handlers
    logger.remove()
    
    # Add console handler
    logger.add(
        lambda msg: print(msg, end=""),
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}\n",
        colorize=False
    )
    
    # Add file handler with timestamped name (no rotation needed)
    logger.add(
        str(log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        backtrace=True,
        diagnose=True
    )
    
    logger.info(f"Logging initialized for date: {date}")
    logger.info(f"Log file: {log_file}")


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
    Now uses centralized configuration.
    """
    from config import settings
    settings.ensure_directories()


def print_asset_summary(results: List["ProcessedResult"], date: str = None) -> None:
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
    
    # Cross-broker position aggregation (optimized with pre-calculated prices)
    summary_lines.append("\n" + "-" * 80)
    summary_lines.append("📊 CROSS-BROKER POSITION SUMMARY:")
    
    # Aggregate positions by stock code - simplified since prices are pre-calculated
    position_aggregation = {}
    for result in results:
        broker_display = f"{result.broker_name}/{result.account_id}" if result.account_id != 'DEFAULT' else result.broker_name
        if result.account_id == 'EXCEL':
            broker_display = result.broker_name
            
        for position in result.positions:
            # For options, use RawDescription for unique identification
            # Otherwise different option contracts with same underlying get merged
            stock_code = position['StockCode']
            if 'OPTION' in stock_code.upper() and position.get('RawDescription'):
                # Use full option description to distinguish different contracts
                unique_key = position['RawDescription']
            else:
                # Use regular stock code for stocks
                unique_key = stock_code
            holding = position['Holding']
            # Ensure holding is numeric
            try:
                holding_num = int(holding) if isinstance(holding, (int, float)) else int(float(str(holding).replace(',', '')))
            except (ValueError, TypeError):
                holding_num = 0
                
            # Use optimized price data if available
            final_price = position.get('FinalPrice')
            final_price_source = position.get('FinalPriceSource', 'N/A')
            price_currency = position.get('OptimizedPriceCurrency') or position.get('PriceCurrency', 'USD')
            
            if unique_key not in position_aggregation:
                position_aggregation[unique_key] = {
                    'total_holding': 0,
                    'brokers': [],
                    'final_price': final_price,
                    'price_source': final_price_source,
                    'price_currency': price_currency,
                    'total_value_usd': 0.0
                }
            
            # Add holding and broker info
            position_aggregation[unique_key]['total_holding'] += holding_num
            position_aggregation[unique_key]['brokers'].append(f"{broker_display}: {holding_num:,}")
            
            # Add position value with currency conversion (preserve original separate calculation logic)
            if final_price is not None:
                # Calculate individual position value with correct multiplier
                multiplier = get_option_multiplier(stock_code, position.get('RawDescription'), position.get('Multiplier'))
                position_value_original = final_price * holding_num * multiplier
                
                if multiplier > 1:
                    logger.debug(f"Applied {multiplier}x option multiplier for {stock_code}: {holding_num} × {final_price} × {multiplier} = {position_value_original}")
                else:
                    logger.debug(f"Stock/OTC calculation for {stock_code}: {holding_num} × {final_price} = {position_value_original}")
                
                # Convert to USD if needed
                if price_currency != 'USD':
                    try:
                        from exchange_rate_handler import exchange_handler
                        usd_rate = exchange_handler.get_rate_lazy(price_currency, 'USD', date)
                        position_value_usd = position_value_original * usd_rate
                    except Exception as e:
                        logger.warning(f"Currency conversion failed for {price_currency}→USD: {e}")
                        logger.warning(f"Using original {price_currency} value without conversion")
                        position_value_usd = position_value_original  # Keep original value, mark as unconverted
                        price_currency = f"{price_currency}_UNCONVERTED"  # Mark for display
                else:
                    position_value_usd = position_value_original
                
                # Accumulate individual position values (this preserves the separate calculation logic)
                position_aggregation[unique_key]['total_value_usd'] += position_value_usd
    
    # Display aggregated positions - much simpler now
    if position_aggregation:
        summary_lines.append("")
        total_portfolio_value = 0.0
        for unique_key in sorted(position_aggregation.keys()):
            agg = position_aggregation[unique_key]
            total_holding = agg['total_holding']
            brokers_str = ", ".join(agg['brokers'])
            
            # Display price and value (using accumulated individual calculations)
            if agg['final_price'] is not None:
                if agg['price_currency'] != 'USD' and not agg['price_currency'].endswith('_UNCONVERTED'):
                    try:
                        from exchange_rate_handler import exchange_handler
                        usd_rate = exchange_handler.get_rate_lazy(agg['price_currency'], 'USD', date)
                        usd_price = agg['final_price'] * usd_rate
                        price_display = f"{agg['final_price']:.2f} {agg['price_currency']} (${usd_price:.2f} USD, {agg['price_source']})"
                    except Exception as e:
                        logger.warning(f"Display conversion failed for {agg['price_currency']}: {e}")
                        price_display = f"{agg['final_price']:.2f} {agg['price_currency']} (Conversion Failed, {agg['price_source']})"
                elif agg['price_currency'].endswith('_UNCONVERTED'):
                    original_currency = agg['price_currency'].replace('_UNCONVERTED', '')
                    price_display = f"{agg['final_price']:.2f} {original_currency} (No USD Conversion, {agg['price_source']})"
                else:
                    price_display = f"{agg['final_price']:.2f} {agg['price_currency']} ({agg['price_source']})"
                
                # Use the accumulated value from individual calculations
                value_display = f"[${agg['total_value_usd']:,.2f}]"
                total_portfolio_value += agg['total_value_usd']
            else:
                price_display = "N/A"
                value_display = "[$0.00]"
            
            # Clean display format
            summary_lines.append(f"   {unique_key}: {total_holding:,} shares (from: {brokers_str})")
            summary_lines.append(f"     → Price: {price_display} {value_display}")
        
        # Add portfolio total
        summary_lines.append(f"\n   📊 Cross-Broker Portfolio Value: ${total_portfolio_value:,.2f} USD")
    else:
        summary_lines.append("   No positions found across all brokers")
    
    # Add totals
    summary_lines.append("\n" + "-" * 80)
    summary_lines.append(f"[TOTAL] Total Cash: ${total_cash_usd:,.2f} USD")
    summary_lines.append(f"[TOTAL] Total Positions: ${total_portfolio_value:,.2f} USD")
    summary_lines.append(f"[TOTAL] Grand Total: ${total_cash_usd + total_portfolio_value:,.2f} USD")
    summary_lines.append("=" * 80)
    
    # Print and log the summary
    summary_text = "\n".join(summary_lines)
    logger.info(f"Asset Summary Report:\n{summary_text}")
    print(summary_text)


# ============================================================================
# Money Market Fund Detection
# ============================================================================

def is_money_market_fund(description: str = None) -> bool:
    """
    Detect if a security is a Money Market Fund
    
    Simply check if 'money market fund' appears in description (case-insensitive)
    
    Args:
        description: Product name/description
    
    Returns:
        True if it's a money market fund, False otherwise
    
    Examples:
        >>> is_money_market_fund('CSOP USD Money Market Fund')
        True
        >>> is_money_market_fund('Apple Inc')
        False
        >>> is_money_market_fund(None)
        False
    """
    if not description:
        return False
    
    return 'money market fund' in description.lower()
