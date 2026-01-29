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

load_dotenv()

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)

app = FastAPI(title="Executive Brain API")

# --- PERMISSIVE CORS FOR PRODUCTION ---
origins = [
    "http://localhost:5173",
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

persistence = PersistenceManager()
assistant = EmailAssistant()

# ------------------------------------------------------------------
# LOGIC HANDLERS (Shared by both prefixed and non-prefixed routes)
# ------------------------------------------------------------------
async def get_accounts_handler():
    return {"status": "connected", "accounts": [], "timestamp": datetime.now().isoformat()}

async def get_process_handler():
    return {"status": "idle", "active_tasks": 0, "system": "operational"}

# ------------------------------------------------------------------
# ROOT LEVEL ROUTES (Handles: /process, /accounts)
# ------------------------------------------------------------------
@app.get("/accounts")
async def root_accounts():
    return await get_accounts_handler()

@app.get("/process")
async def root_process():
    return await get_process_handler()

@app.get("/health")
async def root_health():
    return {"status": "healthy"}

# ------------------------------------------------------------------
# API PREFIXED ROUTES (Handles: /api/process, /api/accounts, /api/threads)
# ------------------------------------------------------------------
api_router = APIRouter(prefix="/api")

@api_router.get("/health")
async def api_health():
    return {"status": "healthy", "scope": "api"}

@api_router.get("/accounts")
async def api_accounts():
    return await get_accounts_handler()

@api_router.get("/process")
async def api_process():
    return await get_process_handler()

@api_router.get("/threads")
async def list_threads():
    threads_list = []
    current_threads = getattr(assistant, 'threads', {})
    for thread_id, thread in current_threads.items():
        summary_obj = getattr(thread, 'current_summary', None)
        if summary_obj:
            raw_text = getattr(summary_obj, 'overview', "No content")
            threads_list.append({
                "thread_id": thread_id,
                "summary": raw_text,
                "confidence_score": getattr(summary_obj, 'confidence_score', 0)
            })
    return {"count": len(threads_list), "threads": threads_list}

app.include_router(api_router)

# ------------------------------------------------------------------
# LIFECYCLE & SOCKET MOUNT
# ------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    try:
        data = persistence.load()
        if data:
            assistant.threads = data.get("threads", {})
    except Exception as e:
        print(f"Startup warning: {e}")

@app.get("/")
async def index():
    return {"message": "Executive Brain Core Online"}

# Socket.IO mounting must remain at the very end
app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")