from ..data.models import ThreadSummary, ClassificationResult
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime


class SummaryResponse(BaseModel):
    thread_id: str
    summary: str
    key_points: List[str]
    action_items: List[str]
    deadlines: List[datetime] = Field(default_factory=list)
    key_participants: List[str] = Field(default_factory=list)
    confidence_score: float = 1.0
    classification: Optional[ClassificationResult] = None


class GmailAuthRequest(BaseModel):
    auth_code: str
    redirect_uri: str


class BatchSummaryRequest(BaseModel):
    message_ids: List[str]


class BatchSummaryResponse(BaseModel):
    summaries: Dict[str, SummaryResponse]
    processing_time_ms: int


class EmailHeaderInfo(BaseModel):
    subject: str
    sender: str
    timestamp: datetime


class EmailDetails(BaseModel):
    id: str
    thread_id: str
    headers: EmailHeaderInfo
    summary: Optional[SummaryResponse] = None


# ------------------------------------------------------------------
# RAW ANALYSIS
# ------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    content: str
    subject: Optional[str] = "Manual Entry"
    sender: Optional[str] = "User"


# ------------------------------------------------------------------
# DRAFT REPLY (MIRRORS ANALYZE)
# ------------------------------------------------------------------

class DraftReplyRequest(BaseModel):
    content: str
    subject: Optional[str] = "Manual Entry"
    sender: Optional[str] = "User"


class DraftReplyResponse(BaseModel):
    draft: str
    confidence_score: float = 0.7


class ThreadInfo(BaseModel):
    thread_id: str
    subject: Optional[str]
    participants: List[str]
    last_updated: datetime
    has_summary: bool
    confidence_score: Optional[float] = None
