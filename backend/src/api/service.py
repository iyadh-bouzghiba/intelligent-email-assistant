import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Request, HTTPException, Response
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
# CORE ROUTES
# ------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat(), "version": "1.1.0"}

@app.get("/")
async def root():
    return {"message": "Secure Email Assistant API is Online", "docs": "/docs"}

@app.get("/threads")
async def list_threads():
    """Returns summarized email threads."""
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

# ------------------------------------------------------------------
# FUTURE-READY AI ROUTES (Silencing Linter Warnings)
# ------------------------------------------------------------------

@app.post("/analyze", response_model=SummaryResponse)
async def analyze_emails(request: AnalyzeRequest):
    """AI Endpoint to analyze specific threads."""
    # Logic will be implemented in Step 4
    return {"thread_id": request.thread_id, "summary": "Analysis pending...", "confidence_score": 1.0}

@app.post("/draft", response_model=DraftReplyResponse)
async def create_draft(request: DraftReplyRequest):
    """AI Endpoint to generate reply drafts."""
    # Logic will be implemented in Step 4
    return {"draft_id": "temp_id", "content": "Drafting logic initializing..."}

# ------------------------------------------------------------------
# LIFECYCLE & MOUNTING
# ------------------------------------------------------------------

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

app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")