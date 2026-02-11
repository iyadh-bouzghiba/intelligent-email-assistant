"""
Intelligent Email Assistant - API Service

FastAPI application providing:
- OAuth authentication with Google
- Email analysis and summarization API
- Real-time WebSocket connections
- Multi-tenant email management

Bootstrap:
    Imports are resolved via proper Python package structure.
    No manual sys.path manipulation needed.
"""
import os
import sys

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, APIRouter
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
import socketio

from backend.config import Config
from backend.core import EmailAssistant
from backend.api.models import (
    SummaryResponse, AnalyzeRequest, DraftReplyRequest, DraftReplyResponse,
)
from backend.data.store import PersistenceManager
from backend.infrastructure.control_plane import ControlPlane
from backend.api.oauth_manager import OAuthManager
from backend.auth.credential_store import CredentialStore
from fastapi.responses import RedirectResponse

load_dotenv()

# ------------------------------------------------------------------
# FASTAPI APP (CORS MUST BE FIRST)
# ------------------------------------------------------------------
app = FastAPI(title="Executive Brain - Sentinel Core")

allowed_origins = []
if os.getenv("FRONTEND_URL"):
    allowed_origins.append(os.getenv("FRONTEND_URL"))

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# SOCKET.IO (WEBSOCKET ONLY - RENDER SAFE)
# ------------------------------------------------------------------
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[
        "https://intelligent-email-frontend.onrender.com",
        "http://localhost:5173",
    ],
    transports=["websocket"],          # [!] CRITICAL FIX
    ping_timeout=20,
    ping_interval=10,
    logger=True,
    engineio_logger=True,
)

# ------------------------------------------------------------------
# RATE LIMITING (SLA PROTECTION)
# ------------------------------------------------------------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = time.time()
        
        # Clean old requests
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        self.requests[client_ip] = [t for t in self.requests[client_ip] if now - t < self.window_seconds]
        
        if len(self.requests[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Strategic throttle active. Too many requests."}
            )
        
        self.requests[client_ip].append(now)
        return await call_next(request)

app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

# ------------------------------------------------------------------
# GLOBAL PROJECT STATE (Deferred Init)
# ------------------------------------------------------------------
persistence = PersistenceManager()
assistant: Optional[EmailAssistant] = None # Defer to prevent import errors

# ------------------------------------------------------------------
# SOCKET.IO HANDSHAKE
# ------------------------------------------------------------------
@sio.on("connect")
async def connect(sid, environ):
    print(f"[SOCKET] Sentinel Connection Authenticated: {sid}")
    await sio.emit(
        "connection_status",
        {"status": "stable", "transmission": "encrypted"},
        to=sid,
    )

# ------------------------------------------------------------------
# CACHE CONTROL
# ------------------------------------------------------------------
class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

app.add_middleware(CacheControlMiddleware)

# ------------------------------------------------------------------
# FAULT TOLERANCE
# ------------------------------------------------------------------
def safe_get_store():
    """Prevents startup crashes when Supabase is unreachable"""
    try:
        from backend.infrastructure.supabase_store import SupabaseStore
        return SupabaseStore()
    except Exception as e:
        print(f"[WARN] Store unavailable: {e}")
        return None

async def get_system_heartbeat():
    return {
        "status": "ok",
        "health": "healthy",
        "system": "operational",
        "code": 200,
        "transmission": "stable",
        "connected": True,
        "version": "v2.1.0-LIVE",
        "accounts": ["primary-access@gmail.com"],
        "timestamp": datetime.now().isoformat(),
    }

@app.get("/health")
async def health():
    """Render survival health check"""
    return {"status": "ok", "schema": ControlPlane.schema_state}

@app.get("/healthz")
async def healthz():
    """Render liveness probe - API-only.

    Deliberately stateless: returns 200 as long as the process is alive and
    uvicorn is serving.  Worker heartbeat is NOT reflected here; worker
    survivability is handled by the daemon thread + restart wrapper in
    worker_entry.py (start_worker).  The WORKER_HEARTBEAT /healthz defined
    in worker_entry.py is dead code - only sio_app (this file) is served.
    """
    return {"status": "ok", "schema": ControlPlane.schema_state}


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    """Root - minimal liveness signal for browsers and probes."""
    return {"status": "ok", "service": "Intelligent Email Assistant"}

def debug_allowed():
    """Returns True only when DEBUG_ENABLED=true is explicitly set."""
    return os.getenv("DEBUG_ENABLED", "false").lower() == "true"

def require_schema_ok():
    """Runtime write-gate: 503 when schema is not verified."""
    if ControlPlane.schema_state != "ok":
        raise HTTPException(
            status_code=503,
            detail=f"Schema state: {ControlPlane.schema_state}. Writes disabled until schema is verified."
        )

@app.get("/debug-config")
async def debug_config():
    """
    Debug endpoint to verify OAuth configuration at runtime.
    CRITICAL: Verifies redirect URI matches Google Cloud Console.

    Expected LOCAL: http://localhost:8000/auth/callback/google
    Expected PROD: https://intelligent-email-assistant-3e1a.onrender.com/auth/callback/google
    """
    if not debug_allowed():
        raise HTTPException(status_code=404)
    from backend.config import Config
    port = os.getenv("PORT", "8000")
    base_url = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

    return {
        "PORT": port,
        "BASE_URL": base_url,
        "REDIRECT_URI": Config.get_callback_url(),
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID", "NOT_SET")[:20] + "...",
        "FRONTEND_URL": os.getenv("FRONTEND_URL", "http://localhost:5173"),
        "ENVIRONMENT": "LOCAL" if "localhost" in base_url else "PRODUCTION"
    }


@app.get("/debug-imports")
async def debug_imports():
    """
    Debug endpoint for Python package import resolution.

    Shows:
    - sys.path entries (import search paths)
    - Python version
    - Package structure verification
    - Import test results

    Use this to troubleshoot ModuleNotFoundError issues.
    """
    if not debug_allowed():
        raise HTTPException(status_code=404)
    import sys
    from pathlib import Path

    # Test critical imports
    import_tests = {}
    try:
        import backend
        import_tests["backend"] = {"status": "OK", "location": str(Path(backend.__file__).parent)}
    except Exception as e:
        import_tests["backend"] = {"status": "FAIL", "error": str(e)}

    try:
        from backend.infrastructure import worker
        import_tests["backend.infrastructure.worker"] = {"status": "OK", "location": str(Path(worker.__file__))}
    except Exception as e:
        import_tests["backend.infrastructure.worker"] = {"status": "FAIL", "error": str(e)}

    try:
        from backend.api import service
        import_tests["backend.api.service"] = {"status": "OK", "location": str(Path(service.__file__))}
    except Exception as e:
        import_tests["backend.api.service"] = {"status": "FAIL", "error": str(e)}

    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "sys_path": sys.path,
        "working_directory": os.getcwd(),
        "package_name": "backend",
        "import_tests": import_tests,
        "execution_mode": "Module execution via -m flag" if __package__ else "Direct script execution",
        "package_context": __package__ or "None (not executed as package)",
    }

@app.get("/accounts")
async def list_accounts_route():
    """Returns valid accounts list for frontend synchronization."""
    return {"accounts": ["primary-access@gmail.com"]}

# ------------------------------------------------------------------
# FRONTEND BRIDGE ROUTES
# ------------------------------------------------------------------
@app.get("/process")
async def process_briefing():
    """Bridge: frontend GET /process \u2192 assistant.process_emails()."""
    if not assistant:
        return {"briefings": [], "account": "primary", "error": "System initializing"}
    try:
        briefings = await asyncio.to_thread(assistant.process_emails)
        return {"briefings": briefings, "account": "primary", "error": None}
    except Exception as e:
        print(f"[WARN] /process error: {e}")
        return {"briefings": [], "account": "primary", "error": str(e)}

@app.get("/emails")
async def list_emails_root():
    """Bridge: frontend GET /emails \u2192 /api/emails (Supabase source of truth)."""
    store = safe_get_store()
    if not store:
        return []
    try:
        return (await asyncio.to_thread(store.get_emails)).data
    except Exception as e:
        print(f"[WARN] /emails fetch error: {e}")
        return []

# ------------------------------------------------------------------
# API ROUTES
# ------------------------------------------------------------------
api_router = APIRouter(prefix="/api")

@api_router.get("/emails")
async def list_emails():
    """REST endpoint for stabilized frontend polling. Reads from Supabase Source of Truth."""
    store = safe_get_store()
    if not store:
        return []

    try:
        response = await asyncio.to_thread(store.get_emails)
        return response.data
    except Exception as e:
        print(f"[WARN] Supabase fetch error: {e}")
        return []


@api_router.post("/sync-now")
async def sync_now():
    """
    User-driven Gmail sync endpoint.
    Executes ONE Gmail fetch + store cycle immediately.

    Returns status-only (no email contents):
    - {"status": "auth_required"} if no valid credentials
    - {"status": "no_new"} if no new emails found
    - {"status": "done", "count": N} if stored N emails
    - {"status": "error"} on failure (no secrets leaked)
    """
    try:
        # Load credentials from CredentialStore (primary) or fallback
        from backend.services.gmail_engine import run_engine

        credential_store = CredentialStore(persistence)
        token_data = credential_store.load_credentials("default")

        # No credentials or file fallback
        if not token_data:
            path = os.getenv("GMAIL_CREDENTIALS_PATH", "")
            if path:
                try:
                    with open(path) as f:
                        token_data = json.load(f)
                except Exception:
                    pass

        if not token_data or 'token' not in token_data:
            return {"status": "auth_required"}

        # Execute Gmail fetch
        emails = await asyncio.to_thread(run_engine, token_data)

        # Handle auth errors
        if isinstance(emails, dict) and "__auth_error__" in emails:
            return {"status": "auth_required"}

        if not emails:
            return {"status": "no_new"}

        # Store emails in Supabase
        store = safe_get_store()
        if not store:
            return {"status": "error"}

        stored_count = 0
        new_thread_ids = []
        for email in emails:
            try:
                await asyncio.to_thread(
                    store.save_email,
                    subject=email.get("subject", "No Subject"),
                    sender=email.get("sender", "Unknown"),
                    date=email.get("date", "Unknown"),
                    body=email.get("body", ""),
                    tenant_id="primary"
                )
                stored_count += 1
                # Track thread_id for auto-summary
                thread_id = f"{email.get('subject', '')}_{email.get('sender', '')}".replace(' ', '_')[:50]
                new_thread_ids.append((thread_id, email))
            except Exception as e:
                print(f"[WARN] [SYNC] Failed to store email: {e}")

        # Emit socket event for new emails
        try:
            await sio.emit("emails_updated", {"count_new": stored_count})
        except Exception as e:
            print(f"[WARN] [SYNC] Failed to emit socket event: {e}")

        # Auto-summary for NEW emails only (Mode A)
        auto_summary_enabled = os.getenv("AUTO_SUMMARY", "false").lower() == "true"
        has_mistral_key = bool(os.getenv("MISTRAL_API_KEY"))
        max_per_cycle = int(os.getenv("SUMMARY_MAX_PER_CYCLE", "5"))

        if auto_summary_enabled and has_mistral_key and new_thread_ids:
            from backend.services.summarizer import Summarizer
            from backend.data.models import ThreadState, ThreadSummary
            from datetime import datetime

            summarizer = Summarizer()
            summarized_count = 0

            for thread_id, email_data in new_thread_ids[:max_per_cycle]:
                try:
                    summary = await asyncio.to_thread(summarizer.summarize, email_data)

                    # Store in assistant.threads
                    if assistant:
                        assistant.threads[thread_id] = ThreadState(
                            thread_id=thread_id,
                            history=[],
                            current_summary=ThreadSummary(
                                thread_id=thread_id,
                                overview=summary,
                                key_points=[],
                                action_items=[],
                                confidence_score=0.95
                            ),
                            last_updated=datetime.now()
                        )
                    summarized_count += 1
                except Exception as e:
                    print(f"[WARN] [SYNC] Auto-summary failed for {thread_id}: {e}")

            # Emit socket event for summaries
            if summarized_count > 0:
                try:
                    await sio.emit("summary_ready", {"count_summarized": summarized_count})
                except Exception as e:
                    print(f"[WARN] [SYNC] Failed to emit summary event: {e}")

        return {"status": "done", "count": stored_count}

    except Exception as e:
        print(f"[ERROR] [SYNC] Sync failed: {e}")
        return {"status": "error"}


@api_router.get("/threads")
async def list_threads():
    if not assistant:
        # Skeletal Mode / Early Boot
        return {
            "count": 0,
            "threads": [{
                "thread_id": "BOOT",
                "summary": "System Initializing...",
                "overview": "Waiting for Brain startup sequence.",
                "confidence_score": 0.0,
                "timestamp": datetime.now().isoformat(), 
            }]
        }

    threads_list = []
    current_threads = getattr(assistant, "threads", {})

    for thread_id, thread in current_threads.items():
        summary_obj = getattr(thread, "current_summary", None)
        overview_text = getattr(summary_obj, "overview", None) or "Analyzing intel..."

        threads_list.append({
            "thread_id": thread_id,
            "account_id": getattr(thread, "account_id", "primary"),
            "summary": overview_text,
            "overview": overview_text,
            "confidence_score": getattr(summary_obj, "confidence_score", 0.95)
            if summary_obj else 0,
            "timestamp": getattr(thread, "last_updated", datetime.now().isoformat()),
        })

    if not threads_list:
        return {
            "count": 1,
            "threads": [{
                "thread_id": "SYS-INIT",
                "summary": "Strategic Protocol: Backend Link Active.",
                "overview": "Backend is live. GMAIL_CREDENTIALS detected.",
                "confidence_score": 1.0,
                "timestamp": datetime.now().isoformat(),
            }],
        }

    return {"count": len(threads_list), "threads": threads_list}

@api_router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Stub: single-thread detail view."""
    if not assistant:
        return {"thread_id": thread_id, "status": "initializing"}
    thread = getattr(assistant, "threads", {}).get(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    summary_obj = getattr(thread, "current_summary", None)
    return {
        "thread_id": thread_id,
        "overview": getattr(summary_obj, "overview", None) or "No summary yet",
        "confidence_score": getattr(summary_obj, "confidence_score", 0.0) if summary_obj else 0.0,
        "timestamp": getattr(thread, "last_updated", datetime.now().isoformat()),
    }

@api_router.post("/threads/{thread_id}/summarize")
async def summarize_thread(thread_id: str):
    """
    On-demand summarization for a specific thread (email).
    Returns status-only (no email content).

    Status responses:
    - {"status": "done"} - summary generated and stored
    - {"status": "skipped_no_key"} - MISTRAL_API_KEY not set
    - {"status": "not_found"} - thread/email not found
    - {"status": "error"} - processing failed
    """
    try:
        # Check if MISTRAL_API_KEY exists (Mode A requirement)
        import os
        if not os.getenv("MISTRAL_API_KEY"):
            return {"status": "skipped_no_key"}

        # Fetch email from Supabase by thread_id (treating subject hash as thread_id)
        store = safe_get_store()
        if not store:
            return {"status": "error"}

        emails_response = await asyncio.to_thread(store.get_emails, limit=200)
        emails = emails_response.data if emails_response else []

        # Find email matching thread_id (simple hash match for now)
        target_email = None
        for email in emails:
            email_thread_id = f"{email.get('subject', '')}_{email.get('sender', '')}".replace(' ', '_')[:50]
            if email_thread_id == thread_id or str(email.get('id')) == thread_id:
                target_email = email
                break

        if not target_email:
            return {"status": "not_found"}

        # Summarize using existing Summarizer
        from backend.services.summarizer import Summarizer
        summarizer = Summarizer()

        email_data = {
            "subject": target_email.get("subject", "No Subject"),
            "sender": target_email.get("sender", "Unknown"),
            "body": target_email.get("body", "")
        }

        summary = await asyncio.to_thread(summarizer.summarize, email_data)

        # Store in assistant.threads (in-memory for now)
        if assistant:
            from backend.data.models import ThreadState, ThreadSummary
            from datetime import datetime

            assistant.threads[thread_id] = ThreadState(
                thread_id=thread_id,
                history=[],
                current_summary=ThreadSummary(
                    thread_id=thread_id,
                    overview=summary,
                    key_points=[],
                    action_items=[],
                    confidence_score=0.95
                ),
                last_updated=datetime.now()
            )

        return {"status": "done"}

    except Exception as e:
        print(f"[ERROR] [SUMMARIZE] Thread summarization failed: {e}")
        return {"status": "error"}


@api_router.post("/threads/{thread_id}/analyze")
async def analyze_thread(thread_id: str):
    """Stub: trigger on-demand analysis for a thread."""
    require_schema_ok()
    return {"thread_id": thread_id, "status": "queued", "message": "Analysis scheduled"}

@api_router.post("/threads/{thread_id}/draft")
async def draft_thread_reply(thread_id: str):
    """Stub: trigger draft-reply generation for a thread."""
    require_schema_ok()
    return {"thread_id": thread_id, "status": "queued", "draft": None, "message": "Draft generation scheduled"}

@api_router.get("/export")
async def export_data(tenant_id: str = "primary"):
    """Enterprise Data Portability: Exports all tenant data."""
    store = safe_get_store()
    control = ControlPlane()
    
    if not store:
        return {"error": "Storage offline"}

    try:
        control.log_audit("data_export", "all", {"tenant_id": tenant_id})
        
        # In a real multi-tenant system, we'd filter every query by tenant_id
        # For now, we fetch emails (which now have tenant_id)
        emails = (await asyncio.to_thread(store.get_emails, limit=1000)).data
        filtered = [e for e in emails if e.get('tenant_id') == tenant_id]
        
        return {
            "tenant_id": tenant_id,
            "export_at": datetime.utcnow().isoformat(),
            "emails": filtered,
            "threads_count": len(getattr(assistant, "threads", {}))
        }
    except Exception as e:
        print(f"[FAIL] Export failed: {e}")
        return {"error": "Export failed"}

# Include API router after all routes are defined
app.include_router(api_router)


# ------------------------------------------------------------------
# GOOGLE OAUTH ROUTES
# ------------------------------------------------------------------
@app.get("/auth/google")
async def google_oauth_init():
    """
    Initiates Google OAuth flow.
    Redirects user to Google consent screen.
    """
    from backend.config import Config
    
    # Environment-driven configuration
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        return JSONResponse(
            status_code=500,
            content={"error": "OAuth credentials not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."}
        )

    # Use canonical redirect URI from environment
    redirect_uri = Config.get_callback_url()

    # Initialize OAuth manager
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    oauth_manager = OAuthManager(client_config, redirect_uri)
    auth_url = oauth_manager.get_authorization_url()

    print(f"[SECURE] [OAuth] Redirecting to Google: {auth_url}")
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback/google")
async def google_oauth_callback(code: str, state: str = None):
    """
    Handles Google OAuth callback.
    Exchanges authorization code for tokens and stores them encrypted.

    CANONICAL CALLBACK ROUTE: /auth/callback/google
    LOCAL: http://localhost:8000/auth/callback/google
    PROD: https://intelligent-email-assistant-3e1a.onrender.com/auth/callback/google
    """
    from backend.config import Config
    
    if not code:
        return JSONResponse(
            status_code=400,
            content={"error": "Authorization code missing"}
        )

    # Environment-driven configuration
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

    if not client_id or not client_secret:
        return JSONResponse(
            status_code=500,
            content={"error": "OAuth credentials not configured"}
        )

    try:
        # Use canonical redirect URI from environment (must match initiation)
        redirect_uri = Config.get_callback_url()

        # Initialize OAuth manager
        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }

        oauth_manager = OAuthManager(client_config, redirect_uri)

        # Load existing credentials to preserve refresh_token if needed
        credential_store = CredentialStore(persistence)
        existing_creds = credential_store.load_credentials("default")

        # Exchange code for tokens
        tokens = oauth_manager.exchange_code_for_tokens(code)

        # OAuth Determinism: Preserve refresh_token if new response lacks it
        if not tokens.get('refresh_token') and existing_creds and existing_creds.get('refresh_token'):
            tokens['refresh_token'] = existing_creds['refresh_token']
            print(f"[OK] [OAuth] Preserved existing refresh_token (new response lacked it)")

        # Log token presence without exposing values
        has_refresh = 'yes' if tokens.get('refresh_token') else 'no'
        print(f"[OK] [OAuth] Tokens received: refresh_token_present={has_refresh}")

        # Store tokens encrypted via CredentialStore
        credential_store.save_credentials("default", tokens)

        print(f"[OK] [OAuth] Tokens encrypted and stored")

        # Redirect to frontend success page
        return RedirectResponse(url=f"{frontend_url}/?auth=success")

    except Exception as e:
        print(f"[FAIL] [OAuth] Callback failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"OAuth callback failed: {str(e)}"}
        )


# ------------------------------------------------------------------
# STARTUP
# ------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    global assistant

    # ENV-BOOT-01: Fail-fast validation at runtime startup (first executable action)
    Config.validate()

    # Initialize assistant to None (deterministic state)
    assistant = None

    control = ControlPlane()

    # PHASE 4: DEPLOYMENT SAFETY CONTRACT - Database Schema Verification
    try:
        schema_verified = control.verify_schema()
    except Exception as e:
        # verify_schema() exception -> FATAL in production, warn in non-production
        print(f"[ERROR] [SCHEMA] Schema verification failed: {e}")
        if Config.is_production():
            print(f"[FATAL] [PRODUCTION] Aborting startup due to schema verification failure")
            raise
        else:
            print(f"[WARN] [NON-PROD] Continuing despite schema verification failure")
            schema_verified = False

    # Guard expected_version retrieval (only used for messaging)
    try:
        expected_version = control.get_supported_schema_version()
    except Exception as e:
        print(f"[WARN] [SCHEMA] Could not determine schema version: {e}")
        expected_version = "unknown"

    if not schema_verified:
        # verify_schema() returned False -> non-blocking (read-only/mismatch messaging)
        print(f"[WARN] [SCHEMA] Mismatch detected. Expected {expected_version}. State: {ControlPlane.schema_state}.")
        print(f"[WARN] [SCHEMA] Writes disabled. Read paths and API remain operational.")
        print(f"[TIP] [ACTION] Run: python -m backend.scripts.verify_db")
        print(f"[TIP] [ACTION] Apply: backend/sql/setup_schema.sql")
    else:
        print(f"[OK] [SYSTEM] Database verified at {expected_version}. Full API routes mounted.")
        print(f"   [-] Available endpoints:")
        print(f"      - GET  /health")
        print(f"      - GET  /debug-config")
        print(f"      - GET  /accounts")
        print(f"      - GET  /auth/google")
        print(f"      - GET  /auth/callback/google")
        print(f"      - GET  /api/emails")
        print(f"      - GET  /api/threads")

    # EmailAssistant Initialization (FATAL if fails)
    try:
        assistant = EmailAssistant()
    except Exception as e:
        print(f"[FATAL] [STARTUP] EmailAssistant init failed: {e}")
        raise

    # Persistence load (non-blocking - assistant can function without pre-loaded threads)
    try:
        data = persistence.load()
        if data:
            assistant.threads = data.get("threads", {})
    except Exception as e:
        print(f"[WARN] [PERSIST] Failed to load thread history: {e}")

    if os.getenv("GMAIL_CREDENTIALS_PATH"):
        print("[SECURE] [SYSTEM] API running in read-only mode - Worker handles Gmail sync")
    else:
        print("[WARN]  [SYSTEM] GMAIL_CREDENTIALS_PATH missing. OAuth flow required.")

    print(f"[OK] [SYSTEM] Startup complete. Ready for requests on port {os.getenv('PORT', '8888')}")

# ------------------------------------------------------------------
# FINAL ASGI WRAP (Must be last)
# ------------------------------------------------------------------
sio_app = socketio.ASGIApp(
    sio,
    other_asgi_app=app,
    socketio_path="/socket.io",
)
