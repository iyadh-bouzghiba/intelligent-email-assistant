from datetime import datetime
from typing import Dict, Any, List, Optional
import os

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# --- FIX: Import main directly since we are in the backend root ---
from main import EmailAssistant

# --- FIX: Standard Absolute Imports from 'src' ---
from src.api.models import (
    SummaryResponse,
    AnalyzeRequest,
    DraftReplyRequest,
    DraftReplyResponse,
)

# Use unified client from integrations
from src.integrations.gmail import GmailClient
from src.api.oauth_manager import OAuthManager

# New Auth Components
from src.auth.credential_store import CredentialStore
from src.auth.token_manager import TokenManager
from src.data.store import PersistenceManager

from src.data.models import ThreadSummary
import socketio


# ------------------------------------------------------------------
# App & Environment
# ------------------------------------------------------------------

load_dotenv()

# Create Socket.IO server for real-time communication
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',  # Tighten in production
    logger=False,
    engineio_logger=False
)

app = FastAPI(title="Secure Email Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
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
assistant = EmailAssistant()

# Global state is now managed by persistence (and injected into assistant)
# We keep references here for easy access in endpoints
GMAIL_WATCH_STATE: Dict[str, Dict[str, Any]] = {}

@app.on_event("startup")
async def startup_event():
    """Load state from disk on startup."""
    print("Loading application state...")
    data = persistence.load()
    
    # 1. Restore Watch State (Tokens handled by CredentialStore)
    global GMAIL_WATCH_STATE
    GMAIL_WATCH_STATE.update(data.get("watch_state", {}))
    
    # 2. Restore Threads into Assistant
    assistant.threads = data.get("threads", {})
    
    print(f"Loaded watch states and {len(assistant.threads)} threads.")

@app.on_event("shutdown")
async def shutdown_event():
    """Save state to disk on shutdown."""
    print("Saving application state...")
    # Trigger a save via persistence manager
    # Note: CredentialStore saves tokens on update. 
    # We explicitly save threads and watch state here.
    
    # Load current tokens to preserve them during this save
    current_disk_state = persistence.load()
    persistence.save(
        tokens=current_disk_state.get("tokens", {}), # Preserve tokens on disk
        watch_state=GMAIL_WATCH_STATE,
        threads=assistant.threads
    )
    print("State saved successfully.")


# ------------------------------------------------------------------
# WebSocket Events
# ------------------------------------------------------------------

@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    print(f"[WebSocket] Client {sid} connected")
    await sio.emit('connection_established', {'status': 'connected'}, room=sid)

@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    print(f"[WebSocket] Client {sid} disconnected")


# Helper function to broadcast thread updates
async def broadcast_thread_update(thread_id: str, summary: dict):
    """Broadcast thread analysis completion to all connected clients."""
    await sio.emit('thread_analyzed', {
        'thread_id': thread_id,
        'summary': summary,
        'timestamp': datetime.utcnow().isoformat()
    })


# ------------------------------------------------------------------
# Gmail Watch State (SAFE – TEMP STORAGE)
# ------------------------------------------------------------------

CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

REDIRECT_URI = os.environ.get(
    "REDIRECT_URI",
    "http://localhost:8000/auth/google/callback"
)

oauth_manager = OAuthManager(CLIENT_CONFIG, REDIRECT_URI)


# ------------------------------------------------------------------
# Core
# ------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "Intelligent Email Assistant API",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


# ------------------------------------------------------------------
# OAuth
# ------------------------------------------------------------------

@app.get("/auth/google/login")
async def login_google():
    auth_url = oauth_manager.get_authorization_url()
    return RedirectResponse(auth_url)


@app.get("/auth/google/callback")
async def callback_google(code: str, response: Response):
    """
    OAuth2 callback with secure JWT token in HttpOnly cookie.
    """
    from src.auth.jwt_service import JWTService
    from src.config import Config
    
    try:
        tokens = oauth_manager.exchange_code_for_tokens(code)
        
        # Use simple user_id for v1
        user_id = "test_user" 
        email_address = tokens.get('email', 'user@example.com') # In prod, extract from ID token
        tokens['email'] = email_address
        
        # Store in CredentialStore
        credential_store.save_credentials(user_id, tokens)
        
        # Create JWT token
        jwt_service = JWTService()
        jwt_token = jwt_service.create_token(user_id=user_id, email=email_address)
        
        # Create redirect response
        frontend_url = Config.FRONTEND_URL or "http://localhost:5173"
        redirect_response = RedirectResponse(url=f"{frontend_url}/?auth=success")
        
        # Set HttpOnly cookie
        redirect_response.set_cookie(
            key="auth_token",
            value=jwt_token,
            httponly=True,
            secure=Config.is_production(), 
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
            path="/"
        )
        
        return redirect_response
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



# ------------------------------------------------------------------
# Gmail Watch – Enable Inbox Push Notifications (STEP 3 – FINAL)
# ------------------------------------------------------------------

@app.post("/gmail/watch")
async def enable_gmail_watch():
    """
    Registers Gmail inbox watch with Pub/Sub.
    """
    user_id = "test_user"

    # 1. Authentication check via TokenManager
    if not token_manager.get_valid_credentials(user_id):
        raise HTTPException(
            status_code=401,
            detail="User not authenticated or tokens expired"
        )

    # 2. Load Pub/Sub topic
    topic_name = os.getenv("GMAIL_PUBSUB_TOPIC") or f"projects/{os.getenv('GCP_PROJECT_ID')}/topics/gmail-events"
    
    try:
        # 3. Initialize Gmail client with valid tokens
        tokens = credential_store.get_credentials(user_id)
        client = GmailClient(tokens)

        # 4. Register Gmail watch
        response = client.start_watch(topic_name=topic_name)

        history_id = response.get("historyId")
        expiration = response.get("expiration")

        if not history_id:
            raise RuntimeError("Gmail watch registration failed (missing historyId)")

        # 5. Persist watch state
        GMAIL_WATCH_STATE[user_id] = {
            "history_id": history_id,
            "email": tokens.get("email"),
            "expiration": expiration,
            "topic": topic_name,
            "started_at": datetime.utcnow().isoformat()
        }
        
        # Update persistence
        # We save watch state alongside tokens (which are already saved)
        persistence.save(credential_store._pm.load().get("tokens",{}), GMAIL_WATCH_STATE, assistant.threads)

        return {
            "status": "watching",
            "history_id": history_id,
            "expiration": expiration
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# THREAD-CENTRIC AI CORE
# ------------------------------------------------------------------

@app.get("/threads")
async def list_threads():
    threads = []

    for thread_id, thread in assistant.threads.items():
        if not thread.current_summary:
            continue

        summary = thread.current_summary
        threads.append({
            "thread_id": summary.thread_id,
            "overview": summary.overview,
            "confidence_score": summary.confidence_score,
            "last_updated": getattr(thread, "last_updated", None)
        })

    return {
        "count": len(threads),
        "threads": threads
    }


@app.get("/threads/{thread_id}", response_model=SummaryResponse)
async def get_thread_summary(thread_id: str):
    thread = assistant.threads.get(thread_id)

    if not thread or not thread.current_summary:
        raise HTTPException(status_code=404, detail="Thread not analyzed")

    summary = thread.current_summary

    return SummaryResponse(
        thread_id=summary.thread_id,
        summary=summary.overview,
        key_points=summary.key_points,
        action_items=summary.action_items,
        deadlines=summary.deadlines,
        key_participants=summary.key_participants,
        confidence_score=summary.confidence_score,
        classification=None
    )


@app.post("/threads/{thread_id}/analyze", response_model=SummaryResponse)
async def analyze_thread(thread_id: str):
    thread = assistant.threads.get(thread_id)

    if not thread or not thread.history: # Check history instead of latest_email
        raise HTTPException(status_code=404, detail="Thread not found")
        
    # Trigger reprocessing (this might re-summarize via DecisionRouter logic in assistant)
    
    summary = assistant.summarizer.summarize_thread(thread)
    thread.current_summary = summary
    
    # Save
    persistence.save(credential_store._pm.load().get("tokens",{}), GMAIL_WATCH_STATE, assistant.threads)
    
    # Broadcast update via WebSocket
    await broadcast_thread_update(thread_id, {
        'thread_id': summary.thread_id,
        'summary': summary.overview,
        'key_points': summary.key_points,
        'action_items': summary.action_items,
        'confidence_score': summary.confidence_score
    })

    return SummaryResponse(
        thread_id=summary.thread_id,
        summary=summary.overview,
        key_points=summary.key_points,
        action_items=summary.action_items,
        deadlines=summary.deadlines,
        key_participants=summary.key_participants,
        confidence_score=summary.confidence_score,
        classification=None
    )


@app.post("/threads/{thread_id}/draft", response_model=DraftReplyResponse)
async def draft_thread_reply(thread_id: str):
    thread = assistant.threads.get(thread_id)

    if not thread or not thread.current_summary:
        raise HTTPException(status_code=404, detail="Thread not ready")
        
    if not thread.history:
         raise HTTPException(status_code=404, detail="No email history")

    draft = assistant.drafter.draft_reply(
        latest_email=thread.history[-1], # Use last email
        summary=thread.current_summary
    )

    return DraftReplyResponse(
        thread_id=thread_id,
        draft=draft
    )

# ------------------------------------------------------------------
# Phase 5: API Exposure Aliases
# ------------------------------------------------------------------

@app.get("/emails")
async def list_emails():
    """Alias for /threads to satisfy Phase 5 requirements."""
    return await list_threads()

@app.get("/emails/{id}/summary")
async def get_email_summary(id: str):
    """Alias for /threads/{id} to satisfy Phase 5 requirements."""
    return await get_thread_summary(id)

@app.post("/emails/{id}/draft")
async def draft_email_reply(id: str):
    """Alias for /threads/{id}/draft to satisfy Phase 5 requirements."""
    return await draft_thread_reply(id)


@app.post("/simulate-email")
async def simulate_email(email_data: dict):
    """
    Simulates an incoming email for demo purposes.
    """
    try:
        analysis = assistant.process_incoming_email(email_data)
        
        # Save state
        persistence.save(credential_store._pm.load().get("tokens",{}), GMAIL_WATCH_STATE, assistant.threads)
        
        return {
            "thread_id": analysis.message_id,
            "status": "processed",
            "summary": analysis.summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Wrap FastAPI with Socket.IO
# ------------------------------------------------------------------
app = socketio.ASGIApp(sio, app)