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
        self.base_output_dir = Path("out") / "pdfs"
    
    def process_pdf(
        self,
        pdf_path: Path,
        broker_name: str,
        account_id: str,
        force: bool = False,
        output_filename: Optional[str] = None
    ) -> Dict:
        """Process a single PDF file."""
        if not pdf_path.exists():
            return {'status': 'error', 'error': f'PDF not found: {pdf_path}'}
        
        if not account_id:
            raise ValueError(f"account_id must be provided for {broker_name}/{pdf_path.name}")
        
        logger.info(f"Processing {broker_name}/{account_id}: {pdf_path.name}")
        
        processed_path = None
        try:
            # Process PDF (decrypt + filter)
            processed_path = self._process_pdf_file(
                pdf_path,
                broker_name,
                account_id,
                force,
                output_filename=output_filename
            )
            final_account_id = account_id
            
            # Get prompt template
            prompt = PROMPT_TEMPLATES.get(broker_name.upper(), PROMPT_TEMPLATES.get('DEFAULT', []))
            
            # Send to LLM
            result = self.llm_handler.process_pdfs_with_prompt(prompt, [str(processed_path)])
            
            return {
                'broker_name': broker_name,
                'account_id': final_account_id,
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
    
    def _process_pdf_file(
        self,
        pdf_path: Path,
        broker_name: str,
        account_id: str,
        force: bool = False,
        output_filename: Optional[str] = None
    ) -> Path:
        """Internal: decrypt and filter PDF if needed."""
        broker_upper = broker_name.upper()
        config = BROKER_CONFIG.get(broker_upper, {})
        password = config.get('password')
        
        if output_filename:
            stem = Path(output_filename).stem
        else:
            stem = f"{broker_upper}_{account_id}"
        target_filename = f"{stem}_processed.pdf"
        output_dir = self.base_output_dir / broker_upper
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / target_filename
        
        if output_path.exists() and not force:
            logger.info(f"📄 Using cached PDF: {output_path.relative_to(Path('out'))}")
            return output_path
        
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
        
        # Create filtered PDF
        writer = PdfWriter()
        for page_idx in keep_pages:
            writer.add_page(reader.pages[page_idx])
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            writer.write(f)
        
        logger.info(f"Saved processed PDF: {output_path.relative_to(Path('out'))} ({total_pages} → {len(keep_pages)} pages)")
        return output_path
