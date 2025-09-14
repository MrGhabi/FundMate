import os
import base64
import json
from dotenv import load_dotenv
import openai
from pydantic import BaseModel
from typing import Optional, Literal, List, Dict, Any
from loguru import logger


class CashStatistic(BaseModel):
    CNY: Optional[str] = None
    HKD: Optional[str] = None
    USD: Optional[str] = None
    Total: Optional[str] = None
    Total_type: Optional[Literal["CNY", "HKD", "USD"]] = None


class PositionStatistic(BaseModel):
    StockCode: str
    Holding: str


class ResultStatistic(BaseModel):
    Cash: CashStatistic
    Positions: list[PositionStatistic]


class LLMHandler:
    """
    Pure LLM interaction handler.
    Handles OpenAI client initialization and structured API calls.
    """
    
    def __init__(self):
        load_dotenv()
        
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.model = os.getenv("LLM_MODEL")
        
        if not all([self.api_key, self.base_url, self.model]):
            raise ValueError("Missing required environment variables: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL")
        
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=120,
            max_retries=3,
        )
    
    def image_to_base64_data_url(self, image_path: str) -> str:
        """Convert image file to base64 data URL"""
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
    
    def process_images_with_prompt(self, prompt: List[Dict[str, Any]], image_paths: List[str]) -> Dict[str, Any]:
        """
        Send prompt and images to LLM and get structured response.
        
        Args:
            prompt: Structured prompt template
            image_paths: List of image file paths
            
        Returns:
            Dict containing parsed LLM response
            
        Raises:
            Exception: If LLM API call fails
        """
        current_prompt = prompt.copy()
        
        # Add all images to prompt
        for img_path in image_paths:
            image_url = self.image_to_base64_data_url(img_path)
            current_prompt.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
        
        try:
            response = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": current_prompt
                    }
                ],
                response_format=ResultStatistic
            )
            
            msg = response.choices[0].message.content
            data = json.loads(msg)
            
            return data
            
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise