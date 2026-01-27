from datetime import datetime
from typing import Dict, Any, List, Optional
import os

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# --- FIX: Updated Import for new structure ---
from src.core import EmailAssistant

# --- FIX: Standard Absolute Imports ---
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
import socketio

# ------------------------------------------------------------------
# App & Environment
# ------------------------------------------------------------------
load_dotenv()

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=False,
    engineio_logger=False
)

app = FastAPI(title="Secure Email Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# State & Persistence
# ------------------------------------------------------------------
persistence = PersistenceManager()
credential_store = CredentialStore(persistence)
token_manager = TokenManager(credential_store)

# Initialize Assistant
assistant = EmailAssistant()
# IMPORTANT: Ensure assistant has a threads storage if core.py doesn't define it in __init__
if not hasattr(assistant, 'threads'):
    assistant.threads = {}

GMAIL_WATCH_STATE: Dict[str, Dict[str, Any]] = {}

@app.on_event("startup")
async def startup_event():
    print("🚀 API Starting: Loading application state...")
    data = persistence.load()
    
    global GMAIL_WATCH_STATE
    GMAIL_WATCH_STATE.update(data.get("watch_state", {}))
    
    # Restore Threads into Assistant
    assistant.threads = data.get("threads", {})
    print(f"✅ Loaded {len(assistant.threads)} threads.")

@app.on_event("shutdown")
async def shutdown_event():
    print("💾 Shutdown: Saving application state...")
    current_disk_state = persistence.load()
    persistence.save(
        tokens=current_disk_state.get("tokens", {}),
        watch_state=GMAIL_WATCH_STATE,
        threads=assistant.threads
    )

# ------------------------------------------------------------------
# WebSocket & OAuth (Logic remains unchanged)
# ------------------------------------------------------------------
# ... [Keeping your existing WebSocket and OAuth routes as they are] ...

# ------------------------------------------------------------------
# THREAD-CENTRIC AI CORE (Refined to match EmailAssistant)
# ------------------------------------------------------------------

@app.get("/threads")
async def list_threads():
    threads_list = []
    # Safety check for threads attribute
    for thread_id, thread in getattr(assistant, 'threads', {}).items():
        if hasattr(thread, 'current_summary') and thread.current_summary:
            summary = thread.current_summary
            threads_list.append({
                "thread_id": thread_id,
                "overview": summary.overview,
                "confidence_score": getattr(summary, 'confidence_score', 0),
                "last_updated": getattr(thread, "last_updated", None)
            })
    return {"count": len(threads_list), "threads": threads_list}

# ... [Rest of your endpoints stay the same, they now point to a valid assistant object] ...

app = socketio.ASGIApp(sio, app)