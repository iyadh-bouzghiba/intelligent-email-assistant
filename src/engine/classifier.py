import json
from typing import Optional
from .nlp_engine import MistralEngine
from .prompts import CLASSIFICATION_PROMPT
from ..data.models import ClassificationResult, EmailMessage

class EmailClassifier:
    def __init__(self, engine: MistralEngine):
        self.engine = engine
        self.schema = """
        {
            "intent": "string (request, follow_up, escalation, scheduling, fyi, support, sales, other)",
            "priority": "string (urgent, high, medium, low)",
            "confidence": "float (0.0 to 1.0)",
            "reasoning": "string"
        }
        """

    def classify(self, email: EmailMessage) -> ClassificationResult:
        prompt = CLASSIFICATION_PROMPT.format(
            subject=email.metadata.subject,
            body=email.content.plain_text
        )
        
        raw_output = self.engine.get_structured_output(prompt, self.schema)
        
        try:
            # Basic cleaning if LLM adds wrappers
            if "```json" in raw_output:
                raw_output = raw_output.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(raw_output)
            return ClassificationResult(**data)
        except Exception as e:
            # Fallback for parsing errors
            return ClassificationResult(
                intent="other",
                priority="medium",
                confidence=0.0,
                reasoning=f"Error parsing LLM output: {str(e)}"
            )
