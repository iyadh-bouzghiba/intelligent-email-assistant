import asyncio
import json
from typing import List
from .nlp_engine import MistralEngine
from .prompts import SUMMARIZATION_PROMPT
from ..data.models import EmailMessage, ThreadSummary, ThreadState


class EmailSummarizer:
    """
    Thread summarization using Mistral Large for complex reasoning.
    Handles long context windows (up to 128k tokens).
    """
    
    def __init__(self, engine: MistralEngine):
        self.engine = engine
    
    def _build_thread_context(self, thread_state: ThreadState, max_tokens: int = 100000) -> str:
        """
        Build thread context with smart truncation if needed.
        
        Args:
            thread_state: The email thread
            max_tokens: Maximum tokens to include (default 100k, well under 128k limit)
            
        Returns:
            Formatted thread history string
        """
        history_parts = []
        total_tokens = 0
        
        # Process emails in reverse (newest first) to prioritize recent context
        for msg in reversed(thread_state.history):
            email_text = f"""From: {msg.metadata.sender}
Subject: {msg.metadata.subject}
Date: {msg.metadata.timestamp}
Body: {msg.content.plain_text}
---"""
            
            email_tokens = self.engine.count_tokens(email_text)
            
            if total_tokens + email_tokens > max_tokens:
                # If we hit the limit, add a truncation notice
                history_parts.insert(0, "[... earlier emails truncated for context length ...]")
                break
            
            history_parts.insert(0, email_text)
            total_tokens += email_tokens
        
        return "\n\n".join(history_parts)
    
    async def summarize_thread_async(self, thread_state: ThreadState) -> ThreadSummary:
        """
        Async thread summarization for parallel processing.
        
        Returns:
            ThreadSummary with overview, key points, action items, etc.
        """
        history_text = self._build_thread_context(thread_state)
        
        prompt = SUMMARIZATION_PROMPT.format(history=history_text)
        prompt += """

Return a JSON object with this exact structure:
{
    "thread_id": "string",
    "overview": "A concise 2-3 sentence summary of the entire thread",
    "key_points": ["Point 1", "Point 2", "Point 3"],
    "action_items": ["Action 1", "Action 2"],
    "deadlines": ["2026-01-20", "2026-01-25"],
    "key_participants": ["person@example.com", "another@example.com"],
    "confidence_score": 0.95
}"""
        
        try:
            # Use mistral-large-latest for complex reasoning
            data = await self.engine.generate_json_async(
                prompt=prompt,
                model="mistral-large-latest",
                max_tokens=1024,
                temperature=0.5,  # Moderate temperature for balanced creativity
                timeout=30  # Longer timeout for complex analysis
            )
            
            # Ensure thread_id matches
            data["thread_id"] = thread_state.thread_id
            
            return ThreadSummary(**data)
            
        except (ValueError, TimeoutError, RuntimeError) as e:
            # Graceful fallback with demo response
            if not self.engine.api_key:
                demo_data = self.engine._generate_demo_response("summary")
                demo_data["thread_id"] = thread_state.thread_id
                return ThreadSummary(**demo_data)
            
            # Error fallback
            return ThreadSummary(
                thread_id=thread_state.thread_id,
                overview=f"Summary generation failed: {str(e)[:100]}",
                key_points=["Error occurred during analysis"],
                action_items=["Retry analysis or contact support"],
                deadlines=[],
                key_participants=[],
                confidence_score=0.0
            )
        except Exception as e:
            # Catch-all fallback
            return ThreadSummary(
                thread_id=thread_state.thread_id,
                overview="Unexpected error during summarization",
                key_points=[str(e)[:200]],
                action_items=["Retry analysis"],
                deadlines=[],
                key_participants=[],
                confidence_score=0.0
            )
    
    def summarize_thread(self, thread_state: ThreadState) -> ThreadSummary:
        """Synchronous wrapper for backward compatibility."""
        return asyncio.run(self.summarize_thread_async(thread_state))
