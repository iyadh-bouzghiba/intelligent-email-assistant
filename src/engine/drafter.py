from .nlp_engine import MistralEngine
from .prompts import DRAFTING_PROMPT
from ..data.models import EmailMessage, ThreadSummary

class EmailDrafter:
    def __init__(self, engine: MistralEngine):
        self.engine = engine

    def draft_reply(self, latest_email: EmailMessage, summary: ThreadSummary) -> str:
        prompt = DRAFTING_PROMPT.format(
            summary=summary.summary,
            sender=latest_email.metadata.sender,
            subject=latest_email.metadata.subject,
            body=latest_email.content.plain_text
        )
        
        return self.engine.generate(prompt, max_new_tokens=300, temperature=0.6)
