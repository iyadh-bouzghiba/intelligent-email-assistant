from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class IntentCategory(str, Enum):
    REQUEST = "request"
    FOLLOW_UP = "follow_up"
    ESCALATION = "escalation"
    SCHEDULING = "scheduling"
    FYI = "fyi"
    SUPPORT = "support"
    SALES = "sales"
    OTHER = "other"

class PriorityLevel(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class EmailMetadata(BaseModel):
    subject: str
    sender: str
    recipients: List[str]
    cc: List[str] = []
    timestamp: datetime
    message_id: str
    thread_id: str
    in_reply_to: Optional[str] = None

class EmailContent(BaseModel):
    plain_text: str
    html: Optional[str] = None
    attachments: List[str] = []

class EmailMessage(BaseModel):
    metadata: EmailMetadata
    content: EmailContent

class ThreadSummary(BaseModel):
    thread_id: str
    overview: str
    key_points: List[str]
    action_items: List[str]
    deadlines: List[datetime] = []
    key_participants: List[str] = []
    confidence_score: float = 1.0

    def text(self) -> str:
        return self.overview

class ClassificationResult(BaseModel):
    intent: IntentCategory
    priority: PriorityLevel
    confidence: float
    reasoning: str

class EmailAnalysis(BaseModel):
    message_id: str
    classification: Optional[ClassificationResult] = None
    summary: Optional[str] = None
    suggested_reply: Optional[str] = None

class ThreadState(BaseModel):
    thread_id: str
    history: List[EmailMessage]
    current_summary: Optional[ThreadSummary] = None
    overall_intent: Optional[IntentCategory] = None
    last_updated: datetime = Field(default_factory=datetime.now)

