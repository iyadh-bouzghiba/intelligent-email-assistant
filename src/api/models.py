from ..data.models import ThreadSummary as SummaryResponse

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
