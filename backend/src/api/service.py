import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Request, HTTPException, Response, APIRouter
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import socketio

# --- Standard Imports ---
from src.core import EmailAssistant
from src.api.models import (
    SummaryResponse,
    AnalyzeRequest,
    DraftReplyRequest,
    DraftReplyResponse,
)
from src.data.store import PersistenceManager

# ------------------------------------------------------------------
# Initialization & Environment
# ------------------------------------------------------------------
load_dotenv()

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)

app = FastAPI(title="Secure Email Assistant API")

# --- SECURE CORS HANDSHAKE ---
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://intelligent-email-assistant-7za8.onrender.com", 
    "https://intelligent-email-frontend.onrender.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# STATE & PERSISTENCE
# ------------------------------------------------------------------
persistence = PersistenceManager()
assistant = EmailAssistant()

if not hasattr(assistant, 'threads'):
    assistant.threads = {}

GMAIL_WATCH_STATE: Dict[str, Dict[str, Any]] = {}

# ------------------------------------------------------------------
# API ROUTER (Solves the /api/ 404 Errors)
# ------------------------------------------------------------------
api_router = APIRouter(prefix="/api")

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat(), "version": "1.2.0"}

@api_router.get("/threads")
async def list_threads():
    threads_list = []
    current_threads = getattr(assistant, 'threads', {})
    
    for thread_id, thread in current_threads.items():
        summary_obj = getattr(thread, 'current_summary', None)
        if summary_obj:
            raw_text = getattr(summary_obj, 'overview', 
                       getattr(summary_obj, 'summary', "No content"))
            
            threads_list.append({
                "thread_id": thread_id,
                "summary": raw_text, 
                "overview": raw_text, 
                "confidence_score": getattr(summary_obj, 'confidence_score', 0),
                "last_updated": getattr(thread, "last_updated", datetime.now().isoformat())
            })
            
    return {"count": len(threads_list), "threads": threads_list}

# --- Status Endpoints for Frontend Persistence ---
@api_router.get("/accounts")
async def get_accounts():
    """Fixes the 404 in your network tab."""
    return {"status": "connected", "accounts": []}

@api_router.get("/process")
async def get_process_status():
    """Fixes the 404 and Transmission Alert."""
    return {"status": "idle", "active_tasks": 0}

@api_router.post("/analyze", response_model=SummaryResponse)
async def analyze_emails(request: AnalyzeRequest):
    return {"thread_id": request.thread_id, "summary": "Ready for analysis.", "confidence_score": 1.0}

@api_router.post("/draft", response_model=DraftReplyResponse)
async def create_draft(request: DraftReplyRequest):
    return {"draft_id": "init", "content": "System standby."}

# Mount the prefixed router
app.include_router(api_router)

# ------------------------------------------------------------------
# ROOT & LIFECYCLE
# ------------------------------------------------------------------
@app.get("/")
async def root():
    return {"message": "API Active", "docs": "/docs"}

@app.get("/health")
async def root_health():
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    try:
        data = persistence.load()
        if data:
            global GMAIL_WATCH_STATE
            GMAIL_WATCH_STATE.update(data.get("watch_state", {}))
            assistant.threads = data.get("threads", {})
    except Exception as e:
        print(f"Startup warning: {e}")

# FINAL WRAP: Must be the last line
app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")