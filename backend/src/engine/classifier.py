import asyncio
from typing import Optional
from .nlp_engine import MistralEngine
from .prompts import CLASSIFICATION_PROMPT
from ..data.models import ClassificationResult, EmailMessage


class EmailClassifier:
    """
    Fast email classification using Mistral Small for low-latency results.
    Uses native JSON mode for guaranteed structured output.
    """
    
    def __init__(self, engine: MistralEngine):
        self.engine = engine
    
    async def classify_async(self, email: EmailMessage) -> ClassificationResult:
        """
        Async classification for parallel processing.
        
        Returns:
            ClassificationResult with intent, priority, confidence, reasoning
        """
        prompt = CLASSIFICATION_PROMPT.format(
            subject=email.metadata.subject,
            body=email.content.plain_text[:2000]  # Limit to 2000 chars for speed
        )
        
        prompt += """

Return a JSON object with this exact structure:
{
    "intent": "one of: request, follow_up, escalation, scheduling, fyi, support, sales, other",
    "priority": "one of: urgent, high, medium, low",
    "confidence": 0.95,
    "reasoning": "Brief explanation of classification"
}"""
        
        try:
            # Use mistral-small-latest for fast classification
            data = await self.engine.generate_json_async(
                prompt=prompt,
                model="mistral-small-latest",
                max_tokens=256,
                temperature=0.3,  # Low temperature for consistent classification
                timeout=10  # Fast timeout for classification
            )
            
            return ClassificationResult(**data)
            
        except (ValueError, TimeoutError, RuntimeError) as e:
            # Graceful fallback on any error
            return ClassificationResult(
                intent="other",
                priority="medium",
                confidence=0.0,
                reasoning=f"Classification failed: {str(e)[:100]}"
            )
        except Exception as e:
            # Catch-all for unexpected errors
            return ClassificationResult(
                intent="other",
                priority="medium",
                confidence=0.0,
                reasoning=f"Unexpected error: {str(e)[:100]}"
            )
    
    def classify(self, email: EmailMessage) -> ClassificationResult:
        """Synchronous wrapper for backward compatibility."""
        return asyncio.run(self.classify_async(email))
