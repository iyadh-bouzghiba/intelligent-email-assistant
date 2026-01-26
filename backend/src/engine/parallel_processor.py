import asyncio
from typing import Tuple, Optional
from .nlp_engine import MistralEngine
from .classifier import EmailClassifier
from .summarizer import EmailSummarizer
from ..data.models import EmailMessage, ThreadState, ClassificationResult, ThreadSummary


class ParallelProcessor:
    """
    Parallel processing engine for email analysis.
    Runs classification and summarization simultaneously for 2x performance.
    """
    
    def __init__(self, engine: MistralEngine):
        self.engine = engine
        self.classifier = EmailClassifier(engine)
        self.summarizer = EmailSummarizer(engine)
    
    async def process_email_parallel(
        self,
        email: EmailMessage,
        thread_state: ThreadState
    ) -> Tuple[Optional[ClassificationResult], ThreadSummary]:
        """
        Process email with parallel classification and summarization.
        
        Args:
            email: The email to classify
            thread_state: The thread to summarize
            
        Returns:
            Tuple of (classification_result, thread_summary)
            
        Performance:
            - Sequential: ~3-5 seconds (classify then summarize)
            - Parallel: ~2-3 seconds (both at once)
        """
        try:
            # Run both operations concurrently
            classification, summary = await asyncio.gather(
                self.classifier.classify_async(email),
                self.summarizer.summarize_thread_async(thread_state),
                return_exceptions=True  # Don't fail if one task errors
            )
            
            # Handle partial failures gracefully
            if isinstance(classification, Exception):
                print(f"[WARN] Classification failed: {classification}")
                classification = None
            
            if isinstance(summary, Exception):
                print(f"[ERROR] Summarization failed: {summary}")
                # Summarization is critical, create fallback
                summary = ThreadSummary(
                    thread_id=thread_state.thread_id,
                    overview="Summarization failed",
                    key_points=[],
                    action_items=[],
                    deadlines=[],
                    key_participants=[],
                    confidence_score=0.0
                )
            
            return classification, summary
            
        except Exception as e:
            print(f"[ERROR] Parallel processing failed: {e}")
            # Return safe defaults
            return None, ThreadSummary(
                thread_id=thread_state.thread_id,
                overview="Processing failed",
                key_points=[],
                action_items=[],
                deadlines=[],
                key_participants=[],
                confidence_score=0.0
            )
    
    def process_email(
        self,
        email: EmailMessage,
        thread_state: ThreadState
    ) -> Tuple[Optional[ClassificationResult], ThreadSummary]:
        """Synchronous wrapper for backward compatibility."""
        return asyncio.run(self.process_email_parallel(email, thread_state))
