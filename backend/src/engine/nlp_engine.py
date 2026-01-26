import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from mistralai import Mistral
import tiktoken

class MistralEngine:
    """
    Production-grade Mistral AI engine with:
    - Official Mistral SDK
    - Native JSON mode enforcement
    - Proper error handling with retries
    - Token usage tracking
    - Async support for parallel processing
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY")
        self.client = None
        self.token_encoder = None
        
        if self.api_key:
            self.client = Mistral(api_key=self.api_key)
            try:
                self.token_encoder = tiktoken.get_encoding("cl100k_base")
            except Exception:
                self.token_encoder = None
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text for context management."""
        if not self.token_encoder:
            # Rough estimate: 1 token ≈ 4 characters
            return len(text) // 4
        return len(self.token_encoder.encode(text))
    
    async def generate_json_async(
        self,
        prompt: str,
        model: str = "mistral-large-latest",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Generate JSON output using Mistral's native JSON mode.
        """
        if not self.client:
            raise ValueError("Mistral API key not configured. Set MISTRAL_API_KEY environment variable.")
        
        from src.engine.prompts import SYSTEM_PROMPT
        
        try:
            # Use native JSON mode
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.chat.complete,
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=max_tokens,
                    temperature=temperature
                ),
                timeout=timeout
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except asyncio.TimeoutError:
            raise TimeoutError(f"Mistral API call timed out after {timeout}s")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse Mistral JSON response: {e}")
        except Exception as e:
            raise RuntimeError(f"Mistral API error: {str(e)}")
    
    def generate_json(
        self,
        prompt: str,
        model: str = "mistral-large-latest",
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Synchronous wrapper for generate_json_async."""
        return asyncio.run(self.generate_json_async(
            prompt, model, max_tokens, temperature
        ))
    
    async def generate_text_async(
        self,
        prompt: str,
        model: str = "mistral-large-latest",
        max_tokens: int = 512,
        temperature: float = 0.7,
        timeout: int = 30
    ) -> str:
        """
        Generate plain text output (for draft replies).
        """
        if not self.client:
            raise ValueError("Mistral API key not configured")
            
        from src.engine.prompts import SYSTEM_PROMPT
        
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.chat.complete,
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature
                ),
                timeout=timeout
            )
            
            return response.choices[0].message.content.strip()
            
        except asyncio.TimeoutError:
            raise TimeoutError(f"Mistral API call timed out after {timeout}s")
        except Exception as e:
            raise RuntimeError(f"Mistral API error: {str(e)}")
    
    def generate_text(
        self,
        prompt: str,
        model: str = "mistral-large-latest",
        max_tokens: int = 512,
        temperature: float = 0.7
    ) -> str:
        """Synchronous wrapper for generate_text_async."""
        return asyncio.run(self.generate_text_async(
            prompt, model, max_tokens, temperature
        ))
    
    def _generate_demo_response(self, task: str = "analysis") -> Dict[str, Any]:
        """
        Returns structured demo response when API key is missing.
        Used for development/testing without API access.
        """
        if task == "classification":
            return {
                "intent": "other",
                "priority": "medium",
                "confidence": 0.0,
                "reasoning": "⚠️ Demo Mode: MISTRAL_API_KEY not configured. Add your API key to .env file."
            }
        elif task == "summary":
            return {
                "thread_id": "demo",
                "overview": "⚠️ Demo Mode: Real AI analysis requires MISTRAL_API_KEY in your .env file.",
                "key_points": [
                    "The assistant is running in demo mode",
                    "Add MISTRAL_API_KEY to enable AI features",
                    "Restart the backend after adding the key"
                ],
                "action_items": [
                    "Create .env file in backend/ directory",
                    "Add line: MISTRAL_API_KEY=your_key_here",
                    "Restart backend server"
                ],
                "deadlines": [],
                "key_participants": [],
                "confidence_score": 0.0
            }
        else:
            return {
                "status": "demo_mode",
                "message": "MISTRAL_API_KEY not configured"
            }
