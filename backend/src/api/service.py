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
from src.integrations.gmail import GmailClient
from src.api.oauth_manager import OAuthManager
from src.auth.credential_store import CredentialStore
from src.auth.token_manager import TokenManager
from src.data.store import PersistenceManager
from src.data.models import ThreadSummary

# ------------------------------------------------------------------
# Initialization & Environment
# ------------------------------------------------------------------
load_dotenv()

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=False,
    engineio_logger=False
)

app = FastAPI(title="Secure Email Assistant API")

# --- UPDATED: Secure CORS Configuration ---
# Only allow your local development and your live production backend URL.
# Once your frontend is deployed, you will add its unique URL here.
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://intelligent-email-assistant-7za8.onrender.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# NEW: REQUIRED RENDER ROUTES (Prevents 404s)
# ------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Essential for Render to confirm the app is live."""
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    """Provides a base response when visiting the URL."""
    return {
        "message": "Secure Email Assistant API is Online",
        "documentation": "/docs",
        "health": "/health"
    }

# ------------------------------------------------------------------
# State & Persistence
# ------------------------------------------------------------------
persistence = PersistenceManager()
credential_store = CredentialStore(persistence)
token_manager = TokenManager(credential_store)

# Initialize Assistant
assistant = EmailAssistant()

# Safety check for threads attribute
if not hasattr(assistant, 'threads'):
    assistant.threads = {}

GMAIL_WATCH_STATE: Dict[str, Dict[str, Any]] = {}

@app.on_event("startup")
async def startup_event():
    print("🚀 API Starting: Loading application state...")
    try:
        data = persistence.load()
        global GMAIL_WATCH_STATE
        GMAIL_WATCH_STATE.update(data.get("watch_state", {}))
        
        # Restore Threads into Assistant
        assistant.threads = data.get("threads", {})
        print(f"✅ Loaded {len(assistant.threads)} threads.")
    except Exception as e:
        print(f"⚠️ Startup warning (Persistence): {e}")

@app.on_event("shutdown")
async def shutdown_event():
    print("💾 Shutdown: Saving application state...")
    try:
        current_disk_state = persistence.load()
        persistence.save(
            tokens=current_disk_state.get("tokens", {}),
            watch_state=GMAIL_WATCH_STATE,
            threads=assistant.threads
        )
    except Exception as e:
        print(f"❌ Shutdown error (Persistence): {e}")

# ------------------------------------------------------------------
# THREAD-CENTRIC AI CORE
# ------------------------------------------------------------------

@app.get("/threads")
async def list_threads():
    threads_list = []
    # Safety check for threads attribute
    for thread_id, thread in getattr(assistant, 'threads', {}).items():
        summary = getattr(thread, 'current_summary', None)
        if summary:
            threads_list.append({
                "thread_id": thread_id,
                "overview": getattr(summary, 'overview', "No summary available"),
                "confidence_score": getattr(summary, 'confidence_score', 0),
                "last_updated": getattr(thread, "last_updated", None)
            })
    return {"count": len(threads_list), "threads": threads_list}

# --- SocketIO App Wrap ---
app = socketio.ASGIApp(sio, app)