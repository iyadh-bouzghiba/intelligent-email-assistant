import uuid
from datetime import datetime
from src.data.models import EmailMessage, EmailMetadata, EmailContent, ThreadState, EmailAnalysis
from src.engine.nlp_engine import MistralEngine
from src.engine.preprocessing import EmailPreprocessor
from src.engine.classifier import EmailClassifier
from src.engine.summarizer import EmailSummarizer
from src.engine.drafter import EmailDrafter

class EmailAssistant:
    def __init__(self):
        self.engine = MistralEngine()
        self.preprocessor = EmailPreprocessor()
        self.classifier = EmailClassifier(self.engine)
        self.summarizer = EmailSummarizer(self.engine)
        self.drafter = EmailDrafter(self.engine)
        self.threads = {} # In-memory context store for demo
        self.summary_cache = {} # (thread_id, last_msg_hash) -> summary

    def _is_trivial(self, body: str) -> bool:
        """Lightweight heuristic to skip trivial/automated emails."""
        trivial_patterns = [r'^Thanks$', r'^Thank you$', r'^Ok$', r'^Confirmed$', r'^Auto:.*']
        import re
        for p in trivial_patterns:
            if re.match(p, body.strip(), re.IGNORECASE):
                return True
        return len(body.split()) < 5

    def process_incoming_email(self, raw_email_data: dict) -> EmailAnalysis:
        # Preprocess
        clean_body = self.preprocessor.process(
            raw_email_data.get("body", ""), 
            is_html=raw_email_data.get("is_html", False)
        )
        
        # Early-Exit for trivial emails
        if self._is_trivial(clean_body):
            return EmailAnalysis(
                message_id=str(uuid.uuid4()),
                classification=None,
                summary="Trivial/No-action email detected.",
                suggested_reply=None
            )
        
        # Create Data Model
        email = EmailMessage(
            metadata=EmailMetadata(
                subject=raw_email_data.get("subject", "No Subject"),
                sender=raw_email_data.get("sender", "Unknown"),
                recipients=raw_email_data.get("recipients", []),
                timestamp=datetime.now(),
                message_id=str(uuid.uuid4()),
                thread_id=raw_email_data.get("thread_id", str(uuid.uuid4()))
            ),
            content=EmailContent(plain_text=clean_body)
        )
        
        # 1. Classify
        classification = self.classifier.classify(email)
        
        # 2. Update Thread State & Summarize
        thread_id = email.metadata.thread_id
        if thread_id not in self.threads:
            self.threads[thread_id] = ThreadState(thread_id=thread_id, history=[])
        
        self.threads[thread_id].history.append(email)
        
        # Cache Check: Hash the current history to avoid re-summarizing
        import hashlib
        history_hash = hashlib.md5("".join([m.content.plain_text for m in self.threads[thread_id].history]).encode()).hexdigest()
        
        if (thread_id, history_hash) in self.summary_cache:
            summary = self.summary_cache[(thread_id, history_hash)]
        else:
            summary = self.summarizer.summarize_thread(self.threads[thread_id])
            self.summary_cache[(thread_id, history_hash)] = summary
            
        self.threads[thread_id].current_summary = summary
        
        # 3. Draft Reply (if relevant)
        draft = None
        if classification.priority in ["urgent", "high"] or classification.intent == "request":
            draft = self.drafter.draft_reply(email, summary)
        
        return EmailAnalysis(
            message_id=email.metadata.message_id,
            classification=classification,
            summary=summary.summary,
            suggested_reply=draft
        )

if __name__ == "__main__":
    # Example Usage
    assistant = EmailAssistant()
    
    sample_email = {
        "subject": "Urgent: Project Deadline Extension?",
        "sender": "client@example.com",
        "body": "Hi there, we are seeing some delays. Can we push the deadline by two days? It is critical for our team.",
        "is_html": False,
        "thread_id": "thread-123"
    }
    
    # Note: In a real environment, you'd need to mock Mistral or have it loaded.
    print("Processing sample email...")
    # analysis = assistant.process_incoming_email(sample_email)
    # print(analysis.json(indent=2))
