#!/usr/bin/env python3
"""
Gemini LLM Handler - Simplified Version
Clean Gemini handler supporting both images and PDF processing
"""

import os
import base64
import json
import requests
from dotenv import load_dotenv
from typing import List, Dict, Any
from loguru import logger


# System prompt for extraction
SYSTEM_PROMPT = """You are a professional broker statement data extraction agent specialized in accurately extracting cash and position information from broker account statement documents.

Core Requirements:
- Absolute precision: Stock codes and numbers must be EXACTLY as shown in the document - carefully distinguish between similar characters like 6 vs 8, 0 vs O, etc.
- Data completeness: Ensure all visible cash and position data are extracted
- Format compliance: Strictly follow JSON format requirements

JSON Output Format:
Return response as valid JSON. ALL NUMERIC VALUES MUST BE NUMBERS, NOT STRINGS.
Structure: {
  "Cash": {
    "CNY": 123.4, 
    "HKD": 123.4, 
    "USD": 123.4, 
    "Total": 234.5, 
    "Total_type": "HKD"
  }, 
  "Positions": [
    {
      "StockCode": "AAPL",
      "Description": "Apple Inc",
      "Holding": 750000, 
      "Price": 150.50, 
      "PriceCurrency": "USD",
      "Multiplier": 1
    }
  ]
}

Critical Notes:
- Stock codes and numbers must be EXACTLY as shown in the document - double-check digits carefully
- Use null for missing values, numbers (not strings) for amounts
- For options: Multiplier is the contract size (per contract), extract if visible in statement
- Ensure extraction precision as this affects asset calculation accuracy"""


class LLMHandler:
    """
    Simplified Gemini LLM Handler
    Supports both image and PDF file processing
    """
    
    def __init__(self):
        load_dotenv()
        
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.model = os.getenv("LLM_MODEL", "gemini-2.5-pro")
        
        if not self.api_key or not self.base_url:
            raise ValueError("Missing LLM_API_KEY or LLM_BASE_URL")
        
        logger.info(f"Initialized Gemini LLMHandler: {self.model}")
    
    def process_images_with_prompt(self, prompt: List[Dict[str, Any]], image_paths: List[str]) -> Dict[str, Any]:
        """
        Process image files, supports PNG/JPG formats
        
        Args:
            prompt: Broker-specific prompt template
            image_paths: List of image file paths
            
        Returns:
            Dict: Parsed extraction results
        """
        return self._process_files(prompt, image_paths, "image")
    
    def process_pdfs_with_prompt(self, prompt: List[Dict[str, Any]], pdf_paths: List[str]) -> Dict[str, Any]:
        """
        Process PDF files directly
        
        Args:
            prompt: Broker-specific prompt template  
            pdf_paths: List of PDF file paths
            
        Returns:
            Dict: Parsed extraction results
        """
        return self._process_files(prompt, pdf_paths, "pdf")
    
    def _process_files(self, prompt: List[Dict[str, Any]], file_paths: List[str], file_type: str) -> Dict[str, Any]:
        """
        Unified file processing method
        
        Args:
            prompt: Prompt template
            file_paths: List of file paths
            file_type: File type ("image" or "pdf")
        """
        # Build user content
        user_content = [{"type": "text", "text": SYSTEM_PROMPT}]
        
        # Add broker-specific prompts
        for part in prompt:
            if part.get("type") == "text":
                user_content.append({"type": "text", "text": part["text"]})
        
        # Add files
        for file_path in file_paths:
            with open(file_path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode('utf-8')
            
            if file_type == "pdf":
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:application/pdf;base64,{file_data}"}
                })
            else:  # image
                user_content.append({
                    "type": "image_url", 
                    "image_url": {"url": f"data:image/png;base64,{file_data}"}
                })
        
        # API call with retry logic
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": 0,
            "max_tokens": 8192
        }
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=120
                )
                
                if response.status_code == 200:
                    break
                else:
                    if attempt < max_retries - 1:
                        logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries}): {response.status_code} - {response.text}")
                        continue
                    else:
                        raise Exception(f"API call failed after {max_retries} attempts: {response.status_code} - {response.text}")
                        
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"API call exception (attempt {attempt + 1}/{max_retries}): {e}")
                    continue
                else:
                    raise Exception(f"API call failed after {max_retries} attempts: {e}")
        
        # Parse response
        content = response.json()['choices'][0]['message']['content']
        return self._parse_json_response(content)
    
    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON response, supports both pure JSON and Markdown format
        """
        # Try direct parsing
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass
        
        # Try extracting from Markdown
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        raise Exception(f"Cannot parse JSON response: {content[:200]}...")