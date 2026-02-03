import asyncio
from .nlp_engine import MistralEngine
from .prompts import DRAFTING_PROMPT
from ..data.models import EmailMessage, ThreadSummary


class EmailDrafter:
    """
    Draft reply generation using Mistral Large for context-aware responses.
    """
    
    def __init__(self, engine: MistralEngine):
        self.engine = engine
    
    async def draft_reply_async(
        self,
        latest_email: EmailMessage,
        summary: ThreadSummary
    ) -> str:
        """
        Async draft generation for parallel processing.
        
        Args:
            latest_email: The most recent email in the thread
            summary: The thread summary for context
            
        Returns:
            Draft reply text
        """
        # Guard: no API key → no drafting
        if not self.engine.api_key:
            return (
                "Draft reply unavailable (MISTRAL_API_KEY not configured). "
                "Please respond manually."
            )
        
        # Normalize inputs
        summary_text = (summary.overview or "").strip()
        sender = (latest_email.metadata.sender or "the sender").strip()
        subject = (latest_email.metadata.subject or "No Subject").strip()
        body = (latest_email.content.plain_text or "").strip()[:2000]  # Limit body length
        
        prompt = DRAFTING_PROMPT.format(
            summary_text=summary_text,
            sender=sender,
            subject=subject,
            body=body
        )
        
        try:
            # Use mistral-large-latest for high-quality drafts
            draft = await self.engine.generate_text_async(
                prompt=prompt,
                model="mistral-large-latest",
                max_tokens=400,
                temperature=0.6,  # Moderate creativity
                timeout=20
            )
            
            return draft
            
        except (ValueError, TimeoutError, RuntimeError) as e:
            # Graceful fallback
            return (
                f"Draft generation failed: {str(e)[:100]}. "
                "Please review the email and respond manually."
            )
        except Exception as e:
            # Catch-all fallback
            return (
                "An unexpected error occurred during draft generation. "
                "Please respond manually."
            )
    
    def draft_reply(
        self,
        latest_email: EmailMessage,
        summary: ThreadSummary
    ) -> str:
        """Synchronous wrapper for backward compatibility."""
        return asyncio.run(self.draft_reply_async(latest_email, summary))
