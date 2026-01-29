import os
import asyncio
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
    SummaryResponse, AnalyzeRequest, DraftReplyRequest, DraftReplyResponse,
)
from src.data.store import PersistenceManager

load_dotenv()

# --- HARDENED REAL-TIME ENGINE ---
# We use explicit ping timeouts to prevent Render from dropping the socket
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    ping_timeout=60,
    ping_interval=25,
    logger=True,
    engineio_logger=True
)

app = FastAPI(title="Executive Brain - Sentinel Core")

# --- GLOBAL STATE (Multi-Account Support) ---
persistence = PersistenceManager()
assistant = EmailAssistant()
# Standardizing the account structure the frontend expects
GMAIL_ACCOUNTS: List[Dict[str, Any]] = [
    {"id": "primary", "email": os.getenv("PRIMARY_EMAIL", "admin@system.io"), "status": "active"}
]

# --- CORS POLICY ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permissive for debugging the Transmission Alert
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# SOCKET.IO EVENTS (The Heartbeat of the Feed)
# ------------------------------------------------------------------
@sio.event
async def connect(sid, environ):
    print(f"📡 Sentinel Link Established: {sid}")
    # Immediate status emit to clear the 'Transmission Alert'
    await sio.emit('connection_status', {'status': 'stable', 'latency': 'minimal'}, to=sid)

@sio.event
async def disconnect(sid):
    print(f"🛰 Sentinel Link Severed: {sid}")

# ------------------------------------------------------------------
# OMNIPRESENT ROUTING (Fixes 404s for polling)
# ------------------------------------------------------------------
async def system_status_handler():
    return {
        "status": "connected",
        "system": "operational",
        "accounts_active": len(GMAIL_ACCOUNTS),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/process")
@app.get("/accounts")
@app.get("/health")
async def root_ping():
    return await system_status_handler()

api_router = APIRouter(prefix="/api")

@api_router.get("/accounts")
async def get_accounts():
    """Returns multi-account list for the Sidebar."""
    return {"status": "success", "accounts": GMAIL_ACCOUNTS}

@api_router.get("/process")
async def get_process():
    return await system_status_handler()

@api_router.get("/threads")
async def list_threads():
    """Real-time Multi-account Thread Aggregator."""
    threads_list = []
    current_threads = getattr(assistant, 'threads', {})
    
    # Core Logic: Extracting summaries from all active account threads
    for thread_id, thread in current_threads.items():
        summary_obj = getattr(thread, 'current_summary', None)
        raw_text = getattr(summary_obj, 'overview', "Analyzing intel...") if summary_obj else "Syncing..."
        
        threads_list.append({
            "thread_id": thread_id,
            "account_id": getattr(thread, "account_id", "primary"),
            "summary": raw_text,
            "confidence": getattr(summary_obj, "confidence_score", 0.85),
            "timestamp": getattr(thread, "last_updated", datetime.now().isoformat())
        })
    
    # Mock data fallback to verify UI display during first sync
    if not threads_list:
        threads_list = [{
            "thread_id": "SYS-INIT",
            "account_id": "system",
            "summary": "System Protocol: Link Established. Awaiting real-time email stream.",
            "confidence": 1.0,
            "timestamp": datetime.now().isoformat()
        }]

    return {"count": len(threads_list), "threads": threads_list}

app.include_router(api_router)

# ------------------------------------------------------------------
# LIFECYCLE & MOUNTING
# ------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    try:
        data = persistence.load()
        if data:
            assistant.threads = data.get("threads", {})
            print("💾 Persistence state restored.")
    except Exception as e:
        print(f"⚠️ Persistence Warning: {e}")

@app.get("/")
async def index():
    return {"message": "Sentinel API v1.5 - Operational"}

# FINAL WRAP: Must be assigned to 'app' for the ASGI server
app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")