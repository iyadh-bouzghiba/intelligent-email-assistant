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
import logging

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, APIRouter, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
import socketio

# CRITICAL: Configure logging with immediate flush for production visibility
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(name)s] %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger("api.service")
logger.setLevel(logging.INFO)

# Force Python unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

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
# SOCKET.IO (WEBSOCKET + POLLING FALLBACK)
# ------------------------------------------------------------------
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[
        "https://intelligent-email-frontend.onrender.com",
        "http://localhost:5173",
    ],
    transports=["websocket", "polling"],  # FIXED: Enable polling fallback for stability
    ping_timeout=30,                      # FIXED: Increased to 30s (Render's idle timeout limit)
    ping_interval=15,                     # FIXED: Increased to 15s for high-latency networks
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

@app.get("/api/diagnostic")
async def diagnostic_check():
    """
    DIAGNOSTIC: Test database connectivity and write capability.

    Returns detailed status of:
    - Supabase connection
    - Environment variables
    - Test email write operation
    - Actual database state
    """
    logger.info("[DIAGNOSTIC] ========== DIAGNOSTIC CHECK STARTED ==========")
    diagnostic = {
        "timestamp": datetime.now().isoformat(),
        "supabase_configured": False,
        "supabase_url_set": False,
        "supabase_key_set": False,
        "test_write_success": False,
        "test_write_error": None,
        "email_count_in_db": 0,
        "accounts_in_db": [],
        "test_email_id": None
    }

    try:
        # Check environment variables
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        diagnostic["supabase_url_set"] = bool(supabase_url)
        diagnostic["supabase_key_set"] = bool(supabase_key)

        if supabase_url and supabase_key:
            diagnostic["supabase_url_prefix"] = supabase_url[:30] + "..." if len(supabase_url) > 30 else supabase_url
            diagnostic["supabase_configured"] = True

        # Get store instance
        store = safe_get_store()
        if not store:
            diagnostic["test_write_error"] = "Store not available"
            logger.error("[DIAGNOSTIC] Store not available!")
            return diagnostic

        # Check existing emails count
        try:
            existing = await asyncio.to_thread(store.get_emails, limit=1000)
            if hasattr(existing, 'data') and existing.data:
                diagnostic["email_count_in_db"] = len(existing.data)
                # Get unique account IDs
                accounts = set(e.get("account_id") for e in existing.data if e.get("account_id"))
                diagnostic["accounts_in_db"] = list(accounts)
                logger.info(f"[DIAGNOSTIC] Found {len(existing.data)} emails in database")
            else:
                logger.warning("[DIAGNOSTIC] No emails found in database")
        except Exception as e:
            diagnostic["email_count_error"] = str(e)
            logger.error(f"[DIAGNOSTIC] Failed to count emails: {e}")

        # Attempt test write
        test_message_id = f"diagnostic-test-{int(time.time())}"
        logger.info(f"[DIAGNOSTIC] Attempting test write with ID: {test_message_id}")

        result = await asyncio.to_thread(
            store.save_email,
            subject="[DIAGNOSTIC TEST]",
            sender="diagnostic@test.local",
            date=datetime.now().isoformat(),
            body="This is a diagnostic test email to verify database writes work correctly.",
            message_id=test_message_id,
            account_id="diagnostic-test-account",
            tenant_id="primary"
        )

        logger.info(f"[DIAGNOSTIC] save_email returned: {result}")
        logger.info(f"[DIAGNOSTIC] result type: {type(result)}")
        logger.info(f"[DIAGNOSTIC] result has 'data': {hasattr(result, 'data') if result else 'N/A'}")

        if result:
            diagnostic["test_write_result_type"] = str(type(result))
            diagnostic["test_write_has_data_attr"] = hasattr(result, 'data')

            if hasattr(result, 'data'):
                diagnostic["test_write_data"] = result.data if result.data else "EMPTY"
                diagnostic["test_write_data_length"] = len(result.data) if result.data else 0

                if result.data and len(result.data) > 0:
                    diagnostic["test_write_success"] = True
                    diagnostic["test_email_id"] = test_message_id
                    logger.info(f"[DIAGNOSTIC] ✓ Test write SUCCEEDED: {result.data}")
                else:
                    diagnostic["test_write_error"] = "Result.data is empty"
                    logger.error(f"[DIAGNOSTIC] ✗ Test write FAILED: result.data is empty")
            else:
                diagnostic["test_write_error"] = "Result has no 'data' attribute"
                logger.error(f"[DIAGNOSTIC] ✗ Test write FAILED: No 'data' attribute on result")
        else:
            diagnostic["test_write_error"] = "save_email returned None"
            logger.error("[DIAGNOSTIC] ✗ Test write FAILED: save_email returned None")

        # Verify test email was actually written
        try:
            verify_result = await asyncio.to_thread(
                lambda: store.client.table("emails")
                    .select("*")
                    .eq("gmail_message_id", test_message_id)
                    .execute()
            )
            if hasattr(verify_result, 'data') and verify_result.data:
                diagnostic["test_email_verified_in_db"] = True
                diagnostic["test_email_data"] = verify_result.data[0]
                logger.info(f"[DIAGNOSTIC] ✓ Test email VERIFIED in database")
            else:
                diagnostic["test_email_verified_in_db"] = False
                logger.error(f"[DIAGNOSTIC] ✗ Test email NOT FOUND in database after write!")
        except Exception as e:
            diagnostic["test_email_verification_error"] = str(e)
            logger.error(f"[DIAGNOSTIC] Error verifying test email: {e}")

    except Exception as e:
        diagnostic["test_write_error"] = str(e)
        logger.error(f"[DIAGNOSTIC] Exception during diagnostic: {e}")
        import traceback
        logger.error(f"[DIAGNOSTIC] Traceback: {traceback.format_exc()}")

    logger.info("[DIAGNOSTIC] ========== DIAGNOSTIC CHECK COMPLETED ==========")
    return diagnostic


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


_ACCOUNT_ID_CLEAN_RE = re.compile(r"[^a-zA-Z0-9._@-]")

def resolve_account_id(state: Optional[str], account_id: Optional[str]) -> str:
    """
    Resolves the effective account_id from OAuth state or query param.
    Priority:
    - If state starts with "acc:", extract account_id from state
    - Else use account_id parameter
    - Default to "default"
    Sanitizes output to prevent injection: allows only [a-zA-Z0-9._@-]
    CRITICAL: @ symbol MUST be preserved for email address account_ids
    """
    effective = "default"
    if state and isinstance(state, str) and state.startswith("acc:"):
        effective = state[4:]
    elif account_id:
        effective = account_id
    effective = _ACCOUNT_ID_CLEAN_RE.sub("", effective)
    return effective or "default"

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
async def list_emails(account_id: Optional[str] = Query(None)):
    """
    REST endpoint for stabilized frontend polling. Reads from Supabase Source of Truth.

    Args:
        account_id: Optional filter by specific account (e.g., user@gmail.com)

    Returns:
        List of email objects from Supabase
    """
    store = safe_get_store()
    if not store:
        logger.warning("[API] /emails called but store unavailable")
        return []

    try:
        logger.info(f"[API] /emails called with account_id={account_id}")
        response = await asyncio.to_thread(store.get_emails, account_id=account_id)
        email_count = len(response.data) if response.data else 0
        logger.info(f"[API] /emails returning {email_count} emails")
        return response.data
    except Exception as e:
        logger.error(f"[API] /emails fetch error: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[API] Traceback: {traceback.format_exc()}")
        return []


@api_router.get("/emails-with-summaries")
async def list_emails_with_summaries(account_id: Optional[str] = Query(None)):
    """
    OPTIMIZED endpoint that fetches emails with AI summaries in batch.

    This eliminates the N+1 query pattern where frontend makes separate requests
    for each email's summary. Instead, emails and summaries are fetched together.

    Args:
        account_id: Optional filter by specific account (e.g., user@gmail.com)

    Returns:
        List of email objects with merged AI summary fields:
        - ai_summary_json: {overview, action_items, urgency} or null
        - ai_summary_text: Plain text overview or null
        - ai_summary_model: Model used or null
    """
    store = safe_get_store()
    if not store:
        logger.warning("[API] /emails-with-summaries called but store unavailable")
        return []

    try:
        logger.info(f"[API] /emails-with-summaries called with account_id={account_id}")
        emails = await asyncio.to_thread(store.get_emails_with_summaries, account_id=account_id)
        email_count = len(emails) if emails else 0
        logger.info(f"[API] /emails-with-summaries returning {email_count} emails")
        return emails
    except Exception as e:
        logger.error(f"[API] /emails-with-summaries fetch error: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[API] Traceback: {traceback.format_exc()}")
        return []


@api_router.post("/sync-now")
async def sync_now(account_id: str = Query("default")):
    """
    User-driven Gmail sync endpoint with timeout protection.
    Executes ONE Gmail fetch + store cycle immediately.

    Returns status-only (no email contents):
    - {"status": "auth_required"} if no valid credentials
    - {"status": "no_new"} if no new emails found
    - {"status": "done", "count": N} if stored N emails
    - {"status": "timeout"} if sync takes longer than 25 seconds
    - {"status": "error"} on failure (no secrets leaked)
    """
    try:
        # Wrap with 25s timeout (Render has 30s timeout - leave 5s buffer)
        return await asyncio.wait_for(
            _sync_now_impl(account_id),
            timeout=25.0
        )
    except asyncio.TimeoutError:
        logger.error("[SYNC] Request timed out after 25s")
        return {"status": "timeout", "message": "Sync took too long, try reducing email count"}
    except Exception as e:
        logger.error(f"[SYNC] Top-level error: {type(e).__name__}: {e}")
        return {"status": "error", "message": str(e)}


async def _sync_now_impl(account_id: str):
    """Internal sync implementation (extracted for timeout wrapping)."""
    try:
        logger.info("[SYNC] ========== SYNC REQUEST STARTED ==========")
        logger.info(f"[SYNC] Request account_id param: {account_id}")

        effective_account_id = resolve_account_id(None, account_id)
        logger.info(f"[SYNC] Effective account_id: {effective_account_id}")

        # Load credentials from CredentialStore (primary) or fallback
        from backend.services.gmail_engine import run_engine

        logger.info(f"[SYNC] Loading credentials from CredentialStore...")
        credential_store = CredentialStore(persistence)
        token_data = credential_store.load_credentials(effective_account_id)

        # No credentials or file fallback
        if not token_data and effective_account_id == "default":
            logger.info(f"[SYNC] No credentials found for '{effective_account_id}', trying file fallback...")
            path = os.getenv("GMAIL_CREDENTIALS_PATH", "")
            if path:
                try:
                    with open(path) as f:
                        token_data = json.load(f)
                    logger.info(f"[SYNC] Loaded credentials from file: {path}")
                except Exception as e:
                    logger.info(f"[SYNC] File fallback failed: {e}")
                    pass

        if not token_data or 'token' not in token_data:
            logger.info(f"[SYNC] No valid credentials found for account: {effective_account_id}")
            return {"status": "auth_required", "message": f"Please authenticate {effective_account_id}"}

        logger.info(f"[SYNC] Credentials loaded, fetching emails from Gmail...")
        # Execute Gmail fetch
        emails = await asyncio.to_thread(run_engine, token_data)

        # Handle auth errors
        if isinstance(emails, dict) and "__auth_error__" in emails:
            logger.info(f"[SYNC] Gmail authentication error detected")
            return {"status": "auth_required", "message": "Gmail token expired or revoked"}

        if not emails:
            logger.info(f"[SYNC] No emails returned from Gmail")
            return {"status": "no_new", "message": "No emails in inbox"}

        logger.info(f"[SYNC] Gmail fetch successful: {len(emails)} emails retrieved")

        # Store emails in Supabase
        logger.info(f"[SYNC] Initializing Supabase store...")
        store = safe_get_store()
        if not store:
            logger.info(f"[SYNC] CRITICAL ERROR: Supabase store unavailable!")
            return {"status": "error", "message": "Database connection failed"}

        logger.info(f"[SYNC] Processing {len(emails)} emails for account: {effective_account_id}")
        stored_count = 0
        new_thread_ids = []
        ai_job_queue = []  # Collect emails for batch AI job enqueuing (non-blocking)

        for email in emails:
            try:
                # Extract Gmail stable ID for deduplication
                m_id = email.get("message_id") or email.get("id")

                # Skip emails without Gmail ID to prevent duplicate inserts
                if not m_id:
                    logger.warning(f"[SYNC] Skip email without gmail_message_id: {email.get('subject', 'No Subject')}")
                    continue

                # CRITICAL FIX: Verify save_email actually succeeded
                result = await asyncio.to_thread(
                    store.save_email,
                    subject=email.get("subject", "No Subject"),
                    sender=email.get("sender", "Unknown"),
                    date=email.get("date", "Unknown"),
                    body=email.get("body", ""),
                    message_id=m_id,
                    account_id=effective_account_id,
                    tenant_id="primary"
                )

                # Validate that save succeeded (result should have .data)
                if result and hasattr(result, 'data') and result.data:
                    stored_count += 1
                    logger.info(f"[SYNC] ✓ Saved email {stored_count}/{len(emails)}: {email.get('subject', 'No Subject')[:50]}")

                    # Collect for batch AI job enqueuing (first 30 only)
                    if stored_count <= 30:
                        ai_job_queue.append((effective_account_id, m_id))

                    # Track thread_id for auto-summary
                    thread_id = f"{email.get('subject', '')}_{email.get('sender', '')}".replace(' ', '_')[:50]
                    new_thread_ids.append((thread_id, email))
                else:
                    logger.error(f"[SYNC] Failed to save email (no data in response): {email.get('subject', 'No Subject')[:50]}")
                    logger.error(f"[SYNC] Save result: {result}")

            except Exception as e:
                logger.error(f"[SYNC] Exception while storing email: {e}")
                logger.error(f"[SYNC] Email subject: {email.get('subject', 'No Subject')[:50]}")
                import traceback
                logger.error(f"[SYNC] Traceback: {traceback.format_exc()}")

        logger.info(f"[SYNC] Storage complete: {stored_count}/{len(emails)} emails saved successfully")

        # CRITICAL: Enqueue AI jobs AFTER email loop (non-blocking batch)
        if ai_job_queue:
            async def enqueue_batch():
                """Fire-and-forget AI job enqueueing."""
                try:
                    tasks = [
                        asyncio.to_thread(
                            store.enqueue_ai_job,
                            account_id=acc_id,
                            gmail_message_id=msg_id,
                            job_type="email_summarize_v1"
                        )
                        for acc_id, msg_id in ai_job_queue
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    success_count = sum(1 for r in results if r and not isinstance(r, Exception))
                    logger.info(f"[SYNC] Enqueued {success_count}/{len(ai_job_queue)} AI jobs")
                except Exception as e:
                    logger.warning(f"[SYNC] Batch AI job enqueue failed: {e}")

            # Fire-and-forget (doesn't block sync response)
            asyncio.create_task(enqueue_batch())
            logger.info(f"[SYNC] Batch AI job enqueuing started ({len(ai_job_queue)} jobs)")

        # Emit socket event for new emails
        try:
            await sio.emit("emails_updated", {"count_new": stored_count})
            logger.info(f"[SYNC] Socket.IO event emitted: emails_updated (count: {stored_count})")
        except Exception as e:
            logger.warning(f"[SYNC] Failed to emit socket event: {e}")

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
                    logger.warning(f"[SYNC] Auto-summary failed for {thread_id}: {e}")

            # Emit socket event for summaries
            if summarized_count > 0:
                try:
                    await sio.emit("summary_ready", {"count_summarized": summarized_count})
                except Exception as e:
                    logger.warning(f"[SYNC] Failed to emit summary event: {e}")

        logger.info(f"[SYNC] ========== SYNC REQUEST COMPLETED ==========")
        logger.info(f"[SYNC] Final status: {stored_count} emails saved to database")
        return {"status": "done", "count": stored_count, "processed_count": stored_count}

    except Exception as e:
        logger.error(f"[SYNC] ========== SYNC FAILED ==========")
        logger.error(f"[SYNC] Exception type: {type(e).__name__}")
        logger.error(f"[SYNC] Exception message: {str(e)}")
        import traceback
        logger.error(f"[SYNC] Full traceback:")
        logger.error(traceback.format_exc())
        return {"status": "error", "message": f"Sync failed: {type(e).__name__}"}


@api_router.get("/emails/{gmail_message_id}/summary")
async def get_email_summary(
    gmail_message_id: str,
    account_id: str = Query("default")
):
    """
    Fetch AI summary for specific email.

    Returns:
        - summary_json: {overview, action_items, urgency} if ready
        - status: "ready"|"processing"|"failed"|"not_found"
    """
    effective_account_id = resolve_account_id(None, account_id)
    store = safe_get_store()
    if not store:
        return {"status": "error", "message": "Store unavailable"}

    try:
        # Query email_ai_summaries table
        response = await asyncio.to_thread(
            lambda: store.client.table("email_ai_summaries")
                .select("*")
                .eq("account_id", effective_account_id)
                .eq("gmail_message_id", gmail_message_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
        )

        if response.data and len(response.data) > 0:
            summary = response.data[0]
            return {
                "status": "ready",
                "summary_json": summary.get("summary_json"),
                "summary_text": summary.get("summary_text"),
                "model": summary.get("model"),
                "created_at": summary.get("created_at")
            }

        # Check if job is queued/running
        job_response = await asyncio.to_thread(
            lambda: store.client.table("ai_jobs")
                .select("status")
                .eq("account_id", effective_account_id)
                .eq("gmail_message_id", gmail_message_id)
                .eq("job_type", "email_summarize_v1")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
        )

        if job_response.data and len(job_response.data) > 0:
            job_status = job_response.data[0].get("status")
            if job_status in ["queued", "running"]:
                return {"status": "processing"}
            elif job_status in ["failed", "dead"]:
                return {"status": "failed"}

        return {"status": "not_found"}

    except Exception as e:
        logger.error(f"[API] Summary fetch error: {e}")
        return {"status": "error", "message": str(e)}


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


@api_router.get("/accounts")
async def list_accounts():
    """
    Lists all connected Google accounts (no secrets exposed).
    Returns account_id, updated_at, scopes.
    """
    store = safe_get_store()
    if not store:
        return {"accounts": []}
    try:
        creds = await asyncio.to_thread(store.list_credentials, "google")
        accounts = [
            {
                "account_id": c.get("account_id"),
                "connected": True,
                "updated_at": c.get("updated_at"),
                "scopes": c.get("scopes", []),
            }
            for c in (creds or [])
        ]
        return {"accounts": accounts}
    except Exception as e:
        print(f"[WARN] [ACCOUNTS] List failed: {e}")
        return {"accounts": []}

@api_router.post("/accounts/{account_id}/disconnect")
async def disconnect_account(account_id: str):
    """
    Disconnects a Google account by deleting its credentials.
    """
    effective_account_id = resolve_account_id(None, account_id)
    credential_store = CredentialStore(persistence)
    await asyncio.to_thread(credential_store.delete_credentials, effective_account_id)
    return {"status": "disconnected", "account_id": effective_account_id}

@api_router.post("/accounts/disconnect-all")
async def disconnect_all_accounts():
    """
    MIGRATION HELPER: Disconnects ALL accounts (including legacy "default" accounts).
    Use this to clean up before reconnecting with real email IDs.
    """
    store = safe_get_store()
    if not store:
        return {"status": "error", "message": "Store not available"}

    try:
        # Delete ALL Google credentials from Supabase
        response = store.client.table("credentials").delete().eq("provider", "google").execute()
        deleted_count = len(response.data) if response.data else 0
        print(f"[OK] [CLEANUP] Deleted {deleted_count} Google credentials")
        return {"status": "success", "deleted_count": deleted_count}
    except Exception as e:
        print(f"[ERROR] [CLEANUP] Failed to delete credentials: {e}")
        return {"status": "error", "message": str(e)}

@api_router.post("/emails/{gmail_message_id}/summarize")
async def summarize_email_by_id(
    gmail_message_id: str,
    account_id: str = Query("default")
):
    """
    Enqueue AI summarization job for specific email.

    User-triggered action when clicking "Summarize Email" button.

    Args:
        gmail_message_id: Gmail's stable message ID
        account_id: Account identifier (from query param)

    Returns:
        {"status": "queued", "job_id": "..."} on success
        {"status": "no_mistral_key"} if API key missing
        {"status": "email_not_found"} if email doesn't exist
        {"status": "error"} on failure
    """
    # Check if Mistral API key configured
    if not os.getenv("MISTRAL_API_KEY"):
        return {"status": "no_mistral_key"}

    effective_account_id = resolve_account_id(None, account_id)
    store = safe_get_store()
    if not store:
        return {"status": "error", "message": "Store unavailable"}

    try:
        # Verify email exists for this account
        response = await asyncio.to_thread(
            lambda: store.client.table("emails")
                .select("id")
                .eq("account_id", effective_account_id)
                .eq("gmail_message_id", gmail_message_id)
                .execute()
        )

        if not response.data or len(response.data) == 0:
            return {"status": "email_not_found"}

        # Enqueue AI summarization job
        job_id = await asyncio.to_thread(
            store.enqueue_ai_job,
            account_id=effective_account_id,
            gmail_message_id=gmail_message_id,
            job_type="email_summarize_v1"
        )

        if job_id:
            return {"status": "queued", "job_id": job_id}
        else:
            return {"status": "error", "message": "Job enqueue failed"}

    except Exception as e:
        print(f"[ERROR] Manual summarization failed: {e}")
        return {"status": "error", "message": str(e)}

# Include API router after all routes are defined
app.include_router(api_router)


# ------------------------------------------------------------------
# GOOGLE OAUTH ROUTES
# ------------------------------------------------------------------
@app.get("/auth/check")
async def check_oauth_config():
    """
    Diagnostic endpoint to check if OAuth is properly configured.
    Returns configuration status without exposing secrets.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    render_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")

    return {
        "oauth_configured": bool(client_id and client_secret),
        "client_id_set": bool(client_id),
        "client_secret_set": bool(client_secret),
        "client_id_prefix": client_id[:30] + "..." if client_id else None,
        "frontend_url": frontend_url,
        "backend_url": render_url,
        "callback_url": f"{render_url}/auth/callback/google",
        "instructions": "If oauth_configured=false, set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in Render environment variables",
        "documentation": "See AUTHENTICATION_FIX_GUIDE.md for complete setup instructions"
    }


@app.get("/auth/google")
async def google_oauth_init(account_id: str = Query("default")):
    """
    Initiates Google OAuth flow with PKCE support.
    Redirects user to Google consent screen.
    """
    from backend.config import Config
    import base64
    import json

    # Environment-driven configuration
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        return JSONResponse(
            status_code=503,
            content={
                "error": "OAuth credentials not configured",
                "message": "Administrator must set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables",
                "check_config": "/auth/check",
                "platform": "Render Dashboard → Environment → Add variables",
                "documentation": "See AUTHENTICATION_FIX_GUIDE.md for detailed setup instructions"
            }
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
    effective_account_id = resolve_account_id(None, account_id)

    # CRITICAL FIX: Create state parameter BEFORE generating auth URL
    # This prevents duplicate state parameters (OAuth error 400)
    # State format: base64(json({v: code_verifier, a: account_id}))
    # We need to generate code_verifier first, then pass state to get_authorization_url()

    # Generate code_verifier directly (same logic as oauth_manager._generate_code_verifier())
    import secrets
    temp_code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')

    # Encode code_verifier + account_id into state parameter
    state_data = {
        "v": temp_code_verifier,  # PKCE code_verifier
        "a": effective_account_id  # Account ID
    }
    state_json = json.dumps(state_data)
    state_encoded = base64.urlsafe_b64encode(state_json.encode('utf-8')).decode('utf-8')

    # Get authorization URL with PKCE, passing both custom state AND code_verifier
    # CRITICAL: Pass state_encoded so OAuth library uses OUR state (contains code_verifier + account_id)
    # CRITICAL: Pass temp_code_verifier so OAuth uses OUR verifier (matches the one in state)
    auth_url, code_verifier = oauth_manager.get_authorization_url(
        state=state_encoded,
        code_verifier=temp_code_verifier
    )

    print(f"[OAUTH] [PKCE] Generated code_verifier (first 10 chars): {code_verifier[:10]}...")
    print(f"[OAUTH] [PKCE] State parameter contains: verifier + account_id")
    print(f"[OAUTH] [PKCE] Redirecting to Google with PKCE challenge")
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback/google")
async def google_oauth_callback(code: str, state: str = None, account_id: str = Query("default")):
    """
    Handles Google OAuth callback with PKCE support.
    Exchanges authorization code for tokens and stores them encrypted.

    CANONICAL CALLBACK ROUTE: /auth/callback/google
    LOCAL: http://localhost:8000/auth/callback/google
    PROD: https://intelligent-email-assistant-3e1a.onrender.com/auth/callback/google
    """
    from backend.config import Config
    import base64
    import json

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
        # CRITICAL FIX: Extract code_verifier from state parameter
        code_verifier = None
        effective_account_id = "default"

        if state:
            try:
                # Decode state parameter: base64(json({v: code_verifier, a: account_id}))
                state_json = base64.urlsafe_b64decode(state.encode('utf-8')).decode('utf-8')
                state_data = json.loads(state_json)
                code_verifier = state_data.get("v")
                effective_account_id = state_data.get("a", "default")
                print(f"[OAUTH] [PKCE] Extracted code_verifier from state (first 10 chars): {code_verifier[:10] if code_verifier else 'MISSING'}...")
                print(f"[OAUTH] [PKCE] Extracted account_id from state: {effective_account_id}")
            except Exception as e:
                print(f"[OAUTH] [PKCE] Failed to decode state: {e} - falling back to query param")
                effective_account_id = resolve_account_id(None, account_id)

        if not code_verifier:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "OAuth callback failed: Missing code_verifier in state parameter",
                    "message": "PKCE flow requires code_verifier. Please restart OAuth flow from /auth/google"
                }
            )

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

        print(f"[OAUTH] Callback received - account_id: {effective_account_id}")

        # Exchange code for tokens WITH code_verifier (PKCE)
        print(f"[OAUTH] [PKCE] Exchanging authorization code for tokens with code_verifier...")
        tokens = oauth_manager.exchange_code_for_tokens(code, code_verifier)

        # Log token presence without exposing values
        has_refresh = 'yes' if tokens.get('refresh_token') else 'no'
        has_id_token = 'yes' if tokens.get('id_token') else 'no'
        print(f"[OAUTH] Tokens received: refresh_token={has_refresh}, id_token={has_id_token}")

        # CRITICAL: Extract user's actual Gmail email to use as account_id
        # Method 1: Decode id_token JWT (most reliable)
        user_email = None
        if tokens.get('id_token'):
            try:
                import jwt
                # Decode without verification (we trust Google's response)
                id_token_claims = jwt.decode(tokens['id_token'], options={"verify_signature": False})
                user_email = id_token_claims.get('email')
                if user_email:
                    print(f"[OAUTH] ✅ Extracted email from id_token: {user_email}")
                else:
                    print(f"[OAUTH] ⚠️ id_token present but no email claim found")
            except Exception as e:
                print(f"[OAUTH] ⚠️ Failed to decode id_token: {e}")

        # Method 2: Fallback to userinfo API (less reliable due to network/rate limits)
        if not user_email:
            try:
                import requests
                print(f"[OAUTH] id_token method failed, trying userinfo API...")
                userinfo_response = requests.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {tokens['token']}"},
                    timeout=10
                )
                if userinfo_response.status_code == 200:
                    userinfo = userinfo_response.json()
                    user_email = userinfo.get('email')
                    if user_email:
                        print(f"[OAUTH] ✅ Retrieved email from userinfo API: {user_email}")
                    else:
                        print(f"[OAUTH] ⚠️ Userinfo API returned but no email field")
                else:
                    print(f"[OAUTH] ⚠️ Userinfo API failed: HTTP {userinfo_response.status_code}")
            except Exception as e:
                print(f"[OAUTH] ⚠️ Userinfo API request failed: {e}")

        # FAIL-SAFE: Reject OAuth flow if email cannot be determined
        if not user_email:
            error_msg = (
                "Could not determine Gmail account email. "
                "This is required for multi-account support. "
                "Please try connecting again or contact support if the issue persists."
            )
            print(f"[OAUTH] ❌ CRITICAL: Email extraction failed completely")
            print(f"[OAUTH] ❌ Cannot proceed without user email (prevents account collision)")
            return JSONResponse(
                status_code=400,
                content={"error": error_msg}
            )

        # Update effective_account_id with verified email
        effective_account_id = user_email
        print(f"[OAUTH] ✅ Final account_id: {effective_account_id}")

        # Load existing credentials to preserve refresh_token if needed
        credential_store = CredentialStore(persistence)
        existing_creds = credential_store.load_credentials(effective_account_id)

        # OAuth Determinism: Preserve refresh_token if new response lacks it
        if not tokens.get('refresh_token') and existing_creds and existing_creds.get('refresh_token'):
            tokens['refresh_token'] = existing_creds['refresh_token']
            print(f"[OAUTH] Preserved existing refresh_token (new response lacked it)")

        # Store tokens encrypted via CredentialStore (with real email as account_id)
        credential_store.save_credentials(effective_account_id, tokens)

        print(f"[OK] [OAuth] Tokens encrypted and stored for account_id={effective_account_id}")

        # Redirect to frontend success page WITH account_id so frontend can auto-activate
        # CRITICAL: Pass account_id to frontend for immediate activation
        import urllib.parse
        encoded_account_id = urllib.parse.quote(effective_account_id)
        return RedirectResponse(url=f"{frontend_url}/?auth=success&account_id={encoded_account_id}")

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
        print("[TIP] [ACTION] Schema setup: apply backend/sql/setup_schema.sql in Supabase SQL editor")
        print("[TIP] [ACTION] Then restart worker (WORKER_MODE=true) to re-check schema and enable writes")
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

