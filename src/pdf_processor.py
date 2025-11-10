#!/usr/bin/env python3
"""
PDF Processor - Simple and Robust
Direct PDF processing for broker statements without image conversion.
Follows Linus's design principles: simple, efficient, and maintainable.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger
import sys

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    logger.error("Install pypdf: pip install pypdf")
    raise

from src.prompt_templates import PROMPT_TEMPLATES


# Broker-specific configurations
BROKER_CONFIG = {
    'MOOMOO': {
        'password': '0592',
        'remove_last_pages': 1,
        'min_pages': 2,
        'advanced_filter': {'threshold': 7, 'keep_first': 3, 'keep_last': 4}
    },
    'LB': {
        'password': '25780592',
        'remove_last_pages': 1,
        'min_pages': 2
    },
    'CICC': {'remove_last_pages': 2, 'min_pages': 3},
    'GS': {'remove_last_pages': 1, 'min_pages': 2},
    'FIRST SHANGHAI': {'remove_last_pages': 1, 'min_pages': 2},
    'HTI': {'remove_last_pages': 2, 'min_pages': 3},
    'HUATAI': {'remove_last_pages': 2, 'min_pages': 3},
    'IB': {'remove_last_pages': 2, 'min_pages': 3},
    'SDICS': {'remove_last_pages': 1, 'min_pages': 2},
    'TFI': {'remove_last_pages': 1, 'min_pages': 2},
    'TIGER': {'remove_last_pages': 2, 'min_pages': 4}
}


def extract_account_id(pdf_path: Path, broker_name: str) -> str:
    """Extract account ID from PDF filename."""
    filename = pdf_path.name
    broker = broker_name.upper()
    
    # CICC: statements_..._TENFU00_..._TO_....pdf
    if broker == "CICC":
        match = re.search(r'_([A-Z0-9]{6,8})_\d{8}_TO_', filename)
        if match:
            return match.group(1)
    
    # MOOMOO: 客户对账单_1234567890_20240701.pdf
    elif broker == "MOOMOO":
        parts = filename.split('_')
        if len(parts) >= 2:
            return parts[1]
    
    # HUATAI/HTI: extract numeric account
    elif broker in ["HUATAI", "HTI"]:
        match = re.search(r'\b\d{8,}\b', filename)
        if match:
            return match.group()
    
    # Generic: try to find alphanumeric ID
    match = re.search(r'[_\-]([A-Z0-9]{6,10})[_\-]', filename)
    if match:
        return match.group(1)
    
    return pdf_path.stem


def filter_page_indices(total_pages: int, broker_name: str) -> List[int]:
    """Get page indices to keep after filtering."""
    config = BROKER_CONFIG.get(broker_name.upper(), {})
    
    # No config = keep all pages
    if not config or total_pages < config.get('min_pages', 1):
        return list(range(total_pages))
    
    pages = list(range(total_pages))
    
    # Remove last pages
    remove_last = config.get('remove_last_pages', 0)
    if remove_last > 0:
        pages = pages[:-remove_last]
    
    # Advanced filtering (MOOMOO special case)
    advanced = config.get('advanced_filter')
    if advanced and len(pages) > advanced['threshold']:
        pages = pages[:advanced['keep_first']] + pages[-advanced['keep_last']:]
    
    return pages


class PDFProcessor:
    """
    Simple PDF processor for broker statements.
    Handles decryption, page filtering, and LLM processing.
    """
    
    def __init__(self, llm_handler):
        self.llm_handler = llm_handler
        self.base_output_dir = Path("out")
    
    def process_pdf(self, pdf_path: Path, broker_name: str, account_id: str = None, force: bool = False) -> Dict:
        """Process a single PDF file."""
        if not pdf_path.exists():
            return {'status': 'error', 'error': f'PDF not found: {pdf_path}'}
        
        # Extract account ID if not provided
        if not account_id:
            account_id = extract_account_id(pdf_path, broker_name)
        
        logger.info(f"Processing {broker_name}/{account_id}: {pdf_path.name}")
        
        processed_path = None
        try:
            # Process PDF (decrypt + filter)
            processed_path = self._process_pdf_file(pdf_path, broker_name, account_id, force)
            
            # Get prompt template
            prompt = PROMPT_TEMPLATES.get(broker_name.upper(), PROMPT_TEMPLATES.get('DEFAULT', []))
            
            # Send to LLM
            result = self.llm_handler.process_pdfs_with_prompt(prompt, [str(processed_path)])
            
            return {
                'broker_name': broker_name,
                'account_id': account_id,
                'status': 'success',
                'data': result
            }
            
        except Exception as e:
            logger.error(f"Failed to process {broker_name}/{account_id}: {e}")
            return {
                'broker_name': broker_name,
                'account_id': account_id,
                'status': 'error',
                'error': str(e)
            }
        
        finally:
            # Note: Processed PDFs are saved to out/ directory, no cleanup needed
            pass
    
    def process_directory(self, pdf_root: str, broker_filter: str = None, force: bool = False) -> List[Dict]:
        """Process all PDFs in directory structure."""
        results = []
        
        for broker_dir in Path(pdf_root).iterdir():
            if not broker_dir.is_dir():
                continue
            
            if broker_filter and broker_dir.name.upper() != broker_filter.upper():
                continue
            
            for pdf_file in broker_dir.glob("*.pdf"):
                result = self.process_pdf(pdf_file, broker_dir.name, force=force)
                results.append(result)
        
        return results
    
    def _process_pdf_file(self, pdf_path: Path, broker_name: str, account_id: str, force: bool = False) -> Path:
        """Internal: decrypt and filter PDF if needed."""
        config = BROKER_CONFIG.get(broker_name.upper(), {})
        password = config.get('password')
        
        # Check if processed file already exists (cache check)
        date_folder = self._extract_date_from_path(pdf_path)
        output_dir = self.base_output_dir / "pdfs" / date_folder / broker_name / account_id
        output_path = output_dir / f"{pdf_path.stem}_processed.pdf"
        
        if output_path.exists() and not force:
            logger.info(f"📄 Using cached PDF: {output_path.relative_to(self.base_output_dir)}")
            return output_path
        
        # If no password and no filtering, use original
        if not password and not config.get('remove_last_pages'):
            return pdf_path
        
        # Open and process PDF
        reader = PdfReader(str(pdf_path))
        
        # Decrypt if needed
        if reader.is_encrypted:
            if not password:
                logger.warning(f"PDF encrypted but no password for {broker_name}")
                return pdf_path
            reader.decrypt(password)
        
        # Filter pages
        total_pages = len(reader.pages)
        keep_pages = filter_page_indices(total_pages, broker_name)
        
        # If keeping all pages and no encryption, return original
        if len(keep_pages) == total_pages and not reader.is_encrypted:
            return pdf_path
        
        # Create filtered PDF
        writer = PdfWriter()
        for page_idx in keep_pages:
            writer.add_page(reader.pages[page_idx])
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            writer.write(f)
        
        logger.info(f"Saved processed PDF: {output_path.relative_to(self.base_output_dir)} ({total_pages} → {len(keep_pages)} pages)")
        return output_path
    
    def _extract_date_from_path(self, pdf_path: Path) -> str:
        """Extract date folder from PDF path, e.g., '2025-02-28'"""
        path_str = str(pdf_path)
        
        # Look for date pattern like '2025-02-28' in path
        date_match = re.search(r'(20\d{2}-\d{2}-\d{2})', path_str)
        if date_match:
            return date_match.group(1)
        
        # Look for date pattern like '20250228' and convert
        date_match = re.search(r'(20\d{6})', path_str)
        if date_match:
            date_str = date_match.group(1)
            # Convert 20250228 to 2025-02-28
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        # Default fallback
        return "unknown-date"
