import os
from pathlib import Path
from pdf2image import convert_from_path
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import re


def extract_account_id(pdf_path: Path, broker_name: str) -> str:
    """
    Extract account ID from PDF filename based on broker-specific patterns.
    
    Args:
        pdf_path: Path to the PDF file
        broker_name: Name of the broker
        
    Returns:
        str: Account ID extracted from filename, or 'DEFAULT' if extraction fails
    """
    filename = pdf_path.name
    broker_upper = broker_name.upper()
    
    if broker_upper == "CICC":
        # Pattern for CICC: statements_..._TENFU00_..._TO_....pdf
        # Extract the account ID like TENFU00, TENFF01, etc.
        match = re.search(r'_([A-Z0-9]{6,8})_\d{8}_TO_', filename)
        if match:
            return match.group(1)
    
    elif broker_upper == "MOOMOO":
        # For MOOMOO, we might need different pattern extraction
        # Can be extended here based on MOOMOO filename patterns
        pass
    
    elif broker_upper == "LB":
        # For LB (Longbridge), can be extended based on their filename patterns
        pass
    
    # If no specific pattern matches, try to extract any alphanumeric sequence
    # that might represent account ID
    match = re.search(r'[_\-]([A-Z0-9]{6,10})[_\-]', filename)
    if match:
        return match.group(1)
    
    # Fallback: use the filename without extension as account ID
    return pdf_path.stem


def filter_moomoo_pages(images: List, broker_name: str) -> List:
    """
    Filter pages for MOOMOO broker according to specific requirements.
    
    Args:
        images: List of PIL Image objects from PDF conversion
        broker_name: Name of the broker
        
    Returns:
        List: Filtered list of images
    """
    if broker_name.upper() != "MOOMOO":
        return images
    
    # Remove last page for MOOMOO
    if len(images) <= 1:
        return images
    
    filtered_images = images[:-1]  # Remove last page
    
    # If remaining pages > 7, keep first 3 + last 4
    if len(filtered_images) > 7:
        first_3 = filtered_images[:3]
        last_4 = filtered_images[-4:]
        filtered_images = first_3 + last_4
    
    return filtered_images


def convert_single_broker(broker_data: Dict) -> Dict:
    """
    Convert PDF to images for a single broker account.
    
    Args:
        broker_data: Dictionary containing broker processing information
        
    Returns:
        Dict: Processing result with status and details
    """
    broker_name = broker_data['broker_name']
    account_id = broker_data.get('account_id', 'DEFAULT')  # Support backward compatibility
    pdf_file = broker_data['pdf_file']
    output_dir = broker_data['output_dir']
    dpi = broker_data['dpi']
    fmt = broker_data['fmt']
    user_password = broker_data['user_password']
    force = broker_data['force']
    
    # Create a display name for logging
    display_name = f"{broker_name}/{account_id}" if account_id != 'DEFAULT' else broker_name
    
    try:
        # Check if images already exist and we're not forcing conversion
        if not force and output_dir.exists():
            existing_images = list(output_dir.glob(f"*.{fmt}"))
            if existing_images:
                logger.info(f"{display_name} - Images already exist (found {len(existing_images)} files)")
                return {
                    'broker_name': broker_name,
                    'account_id': account_id,
                    'status': 'skipped',
                    'message': f'Images already exist ({len(existing_images)} files)',
                    'pages_converted': len(existing_images)
                }
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Convert PDF to images
        action = "Re-processing" if force and output_dir.exists() else "Processing"
        logger.info(f"{action}: Converting {pdf_file} for {display_name}")
        
        images = convert_from_path(
            str(pdf_file),
            dpi=dpi,
            fmt=fmt,
            userpw=user_password
        )
        
        # Filter images for MOOMOO broker
        original_count = len(images)
        images = filter_moomoo_pages(images, broker_name)
        
        # Log filtering information for MOOMOO
        if broker_name.upper() == "MOOMOO" and len(images) != original_count:
            logger.info(f"{display_name} - Filtered pages: {original_count} → {len(images)} (removed unnecessary pages)")
        
        # Save images
        for i, image in enumerate(images):
            output_path = output_dir / f"page_{i + 1}.{fmt}"
            image.save(output_path, fmt.upper())
        
        logger.success(f"{display_name} - Saved {len(images)} pages to {output_dir}")
        
        return {
            'broker_name': broker_name,
            'account_id': account_id,
            'status': 'success',
            'message': f'Successfully converted {len(images)} pages',
            'pages_converted': len(images)
        }
        
    except Exception as e:
        logger.error(f"{display_name} - Failed to process {pdf_file}: {e}")
        return {
            'broker_name': broker_name,
            'account_id': account_id,
            'status': 'error',
            'message': str(e),
            'pages_converted': 0
        }


def prepare_broker_tasks(pdf_root: Path, image_root: Path, dpi: int, fmt: str, 
                        broker_filter: Optional[str], force: bool) -> List[Dict]:
    """
    Prepare broker processing tasks for concurrent execution.
    Now supports multiple accounts per broker by processing all PDF files.
    
    Args:
        pdf_root: Root directory containing broker subdirectories with PDFs
        image_root: Output directory for converted images
        dpi: Resolution for image conversion
        fmt: Image format (png, jpg, etc.)
        broker_filter: Optional broker name to process only that broker
        force: If False, skip conversion if images already exist
        
    Returns:
        List[Dict]: List of broker task dictionaries (one per PDF/account)
    """
    broker_tasks = []
    
    for subdir in pdf_root.iterdir():
        if not subdir.is_dir():
            continue

        # Apply broker filter if specified
        if broker_filter and subdir.name.upper() != broker_filter.upper():
            continue

        pdf_files = list(subdir.glob("*.pdf"))
        if not pdf_files:
            logger.warning(f"Skipping {subdir} (no PDF files found)")
            continue

        broker_name = subdir.name
        
        # Process ALL PDF files in the directory (support multiple accounts)
        for pdf_file in pdf_files:
            # Extract account ID from PDF filename
            account_id = extract_account_id(pdf_file, broker_name)
            
            # Create account-specific output directory structure
            # Format: image_root/broker_name/account_id/
            relative_subdir = subdir.relative_to(pdf_root)
            output_dir = image_root / relative_subdir / account_id
            
            # Set password for specific brokers if needed
            folder_name = subdir.name.upper()
            if folder_name == "MOOMOO":
                user_password = "0592"
            elif folder_name == "LB":
                user_password = "25780592"
            else:
                user_password = None
            
            broker_task = {
                'broker_name': broker_name,
                'account_id': account_id,  # New field to track account
                'pdf_file': pdf_file,
                'output_dir': output_dir,
                'dpi': dpi,
                'fmt': fmt,
                'user_password': user_password,
                'force': force
            }
            broker_tasks.append(broker_task)
            
            logger.info(f"Prepared task for {broker_name}/{account_id}: {pdf_file.name}")
    
    return broker_tasks


def convert_pdf_directory(pdf_root: str, image_root: str, dpi: int = 300, fmt: str = "png", 
                         broker_filter: str = None, force: bool = True, max_workers: int = 9):
    """
    Convert PDFs to images with concurrent processing at broker level.
    
    Args:
        pdf_root: Root directory containing broker subdirectories with PDFs
        image_root: Output directory for converted images
        dpi: Resolution for image conversion
        fmt: Image format (png, jpg, etc.)
        broker_filter: Optional broker name to process only that broker
        force: If False, skip conversion if images already exist
        max_workers: Maximum number of concurrent broker processors
    """
    pdf_root = Path(pdf_root)
    image_root = Path(image_root)
    
    # Prepare broker tasks
    broker_tasks = prepare_broker_tasks(pdf_root, image_root, dpi, fmt, broker_filter, force)
    
    if not broker_tasks:
        logger.warning("No broker tasks found to process")
        return
    
    logger.info(f"Starting concurrent PDF conversion for {len(broker_tasks)} accounts (max_workers={max_workers})")
    
    # Process broker accounts concurrently
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all broker tasks (now one per account)
        future_to_task = {
            executor.submit(convert_single_broker, task): task
            for task in broker_tasks
        }
        
        # Process completed tasks
        completed_count = 0
        total_accounts = len(broker_tasks)
        
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            broker_name = task['broker_name']
            account_id = task.get('account_id', 'DEFAULT')
            display_name = f"{broker_name}/{account_id}" if account_id != 'DEFAULT' else broker_name
            completed_count += 1
            
            try:
                result = future.result()
                results.append(result)
                logger.info(f"Progress: {completed_count}/{total_accounts} accounts processed")
            except Exception as e:
                logger.error(f"Account {display_name} failed during concurrent processing: {e}")
                results.append({
                    'broker_name': broker_name,
                    'account_id': account_id,
                    'status': 'error',
                    'message': f'Concurrent processing failed: {e}',
                    'pages_converted': 0
                })
    
    # Summary report
    successful = [r for r in results if r['status'] == 'success']
    skipped = [r for r in results if r['status'] == 'skipped']
    failed = [r for r in results if r['status'] == 'error']
    total_pages = sum(r['pages_converted'] for r in results)
    
    logger.info(f"PDF conversion completed: {len(successful)} successful, {len(skipped)} skipped, {len(failed)} failed")
    logger.info(f"Total pages converted: {total_pages}")
    
    if failed:
        failed_accounts = []
        for r in failed:
            broker_name = r['broker_name']
            account_id = r.get('account_id', 'DEFAULT')
            display_name = f"{broker_name}/{account_id}" if account_id != 'DEFAULT' else broker_name
            failed_accounts.append(display_name)
        logger.warning(f"Failed accounts: {failed_accounts}")


# Backward compatibility: keep the original function signature
# def convert_pdf_directory_sequential(pdf_root: str, image_root: str, dpi: int = 300, fmt: str = "png", 
#                                    broker_filter: str = None, force: bool = True):
#     """
#     Sequential version of PDF conversion (for backward compatibility).
#     Uses the concurrent version with max_workers=1.
#     """
#     convert_pdf_directory(pdf_root, image_root, dpi, fmt, broker_filter, force, max_workers=1)
