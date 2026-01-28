import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
# CORRECT IMPORT: Starlette is the core dependency that guarantees this works on Render
from starlette.middleware.proxied_headers import ProxiedHeadersMiddleware
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
    logger=True,
    engineio_logger=True
)

app = FastAPI(title="Secure Email Assistant API")

# Professional Proxy Middleware: Ensures HTTPS recognition behind Render's Load Balancer
app.add_middleware(ProxiedHeadersMiddleware, trusted_hosts="*")

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
credential_store = CredentialStore(persistence)
token_manager = TokenManager(credential_store)
assistant = EmailAssistant()

if not hasattr(assistant, 'threads'):
    assistant.threads = {}

GMAIL_WATCH_STATE: Dict[str, Dict[str, Any]] = {}

# ------------------------------------------------------------------
# CORE ROUTES (Registered BEFORE SocketIO Wrap)
# ------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "version": "1.1.0"
    }

@app.get("/")
async def root():
    return {
        "message": "Secure Email Assistant API is Online",
        "documentation": "/docs",
        "health": "/health"
    }

@app.get("/threads")
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

# ------------------------------------------------------------------
# LIFECYCLE EVENTS
# ------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    print("🚀 API Starting: Loading application state...")
    try:
        data = persistence.load()
        global GMAIL_WATCH_STATE
        GMAIL_WATCH_STATE.update(data.get("watch_state", {}))
        assistant.threads = data.get("threads", {})
        print(f"✅ State loaded successfully.")
    except Exception as e:
        print(f"⚠️ Startup warning: {e}")

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
        print(f"❌ Shutdown error: {e}")

# ------------------------------------------------------------------
# FINAL MOUNTING
# ------------------------------------------------------------------
app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")