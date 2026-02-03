from typing import Optional, Tuple
from backend.data.models import EmailMessage, ClassificationResult, IntentCategory, PriorityLevel
from backend.engine.summarizer import EmailSummarizer
from backend.engine.drafter import EmailDrafter
from backend.data.models import ThreadSummary

class DecisionRouter:
    """
    Routes email to appropriate AI components based on intent and priority.
    """
    def __init__(self, summarizer: EmailSummarizer, drafter: EmailDrafter):
        self.summarizer = summarizer
        self.drafter = drafter

    def route(self, email: EmailMessage, classification: Optional[ClassificationResult], thread_state: Optional[object] = None) -> Tuple[Optional[ThreadSummary], Optional[str]]:
        """
        Decides on actions:
        1. Always Summarize (if thread context exists or new thread)
        2. Draft if Actionable & High Priority
        
        Returns:
            (summary, draft_reply)
        """
        
        # 1. Summarization (Always happens for non-trivial emails, handled before routing usually, 
        # but if we route TO summarizer, we do it here.)
        # The assistant currently summarizes *thread*, so we need thread state.
        # If thread_state is passed, we summarize.
        
        summary = None
        if thread_state:
             summary = self.summarizer.summarize_thread(thread_state)

        # 2. Drafting Decision
        draft = None
        if classification:
             if self._should_draft(classification):
                 # Draft needs summary context usually
                 if summary:
                     draft = self.drafter.draft_reply(email, summary)
        
        return summary, draft

    def _should_draft(self, classification: ClassificationResult) -> bool:
        """
        Determines if we should auto-draft a reply.
        Policy:
        - Intents: REQUEST, SCHEDULING, FOLLOW_UP, SALES
        - Priority: URGENT, HIGH (and sometimes MEDIUM if Request)
        """
        
        # Strict rules for demo/v1
        is_actionable_intent = classification.intent in [
            IntentCategory.REQUEST, 
            IntentCategory.SCHEDULING, 
            IntentCategory.FOLLOW_UP
        ]
        
        is_high_priority = classification.priority in [
            PriorityLevel.URGENT, 
            PriorityLevel.HIGH
        ]
        
        return is_actionable_intent and (is_high_priority or classification.intent == IntentCategory.REQUEST)
