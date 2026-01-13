from typing import List
from .nlp_engine import MistralEngine
from .prompts import SUMMARIZATION_PROMPT
from ..data.models import EmailMessage, ThreadSummary, ThreadState

class EmailSummarizer:
    def __init__(self, engine: MistralEngine):
        self.engine = engine
        self.schema = """
        {
            "thread_id": "string",
            "overview": "string",
            "key_points": ["string"],
            "action_items": ["string"],
            "deadlines": ["ISO8601 string"],
            "key_participants": ["string"],
            "confidence_score": "float"
        }
        """

    def summarize_thread(self, thread_state: ThreadState) -> ThreadSummary:
        history_text = "\n---\n".join([
            f"From: {msg.metadata.sender}\nSubject: {msg.metadata.subject}\nBody: {msg.content.plain_text}"
            for msg in thread_state.history
        ])
        
        prompt = SUMMARIZATION_PROMPT.format(history=history_text)
        raw_output = self.engine.get_structured_output(prompt, self.schema)
        
        try:
            if "```json" in raw_output:
                raw_output = raw_output.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(raw_output)
            # Simple parsing for thread summary
            return ThreadSummary(**data)
        except Exception:
            # Fallback
            return ThreadSummary(
                thread_id=thread_state.thread_id,
                overview="Failed to generate summary.",
                key_points=[],
                action_items=[],
                key_participants=[],
                confidence_score=0.0
            )

import json # Added missing import
