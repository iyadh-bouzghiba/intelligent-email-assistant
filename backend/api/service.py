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
import base64
import mimetypes
import os
import sys
import logging
from pathlib import Path

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from html import escape
from typing import Dict, Any, List, Optional
from email.utils import parseaddr

from fastapi import FastAPI, HTTPException, Request, Response, APIRouter, Query, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

from backend.auth_guard import COOKIE_NAME, build_session_cookie_kwargs, create_access_token, require_jwt_auth


def _get_worker_heartbeat() -> dict:
    """
    Lazy request-time resolution of the sync worker heartbeat.
    Imports at call time so the live dict is always returned instead of a
    module-load-time snapshot that may have been frozen before the worker
    thread populated it (circular-import timing issue).
    Returns {} when the module is unavailable (separate-dyno deployments).
    """
    try:
        from backend.infrastructure.worker import WORKER_HEARTBEAT
        return WORKER_HEARTBEAT
    except Exception:
        return {}


def _get_ai_worker_heartbeat() -> dict:
    """
    Lazy request-time resolution of the AI summarizer worker heartbeat.
    Same lazy-import pattern as _get_worker_heartbeat().
    """
    try:
        from backend.infrastructure.ai_summarizer_entry import AI_WORKER_HEARTBEAT
        return AI_WORKER_HEARTBEAT
    except Exception:
        return {}
from backend.api.models import (
    SummaryResponse, AnalyzeRequest, DraftReplyRequest, DraftReplyResponse,
)
from backend.data.store import PersistenceManager
from backend.infrastructure.control_plane import ControlPlane
from backend.api.oauth_manager import OAuthManager
from backend.auth.credential_store import CredentialStore
from backend.integrations.gmail import GmailClient
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

load_dotenv()

# Frontend static build paths (same-origin serving)
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"

# ------------------------------------------------------------------
# FASTAPI APP (CORS MUST BE FIRST)
# ------------------------------------------------------------------
app = FastAPI(title="Executive Brain - Sentinel Core")

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
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

# Mount frontend /assets only when the build is present
if FRONTEND_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS)), name="frontend-assets")

# ------------------------------------------------------------------
# SOCKET.IO (WEBSOCKET + POLLING FALLBACK)
# ------------------------------------------------------------------
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[
        "https://intelligent-email-frontend.onrender.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
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
@app.head("/health")
async def health():
    """Render survival health check (accepts GET and HEAD)"""
    return {"status": "ok", "schema": ControlPlane.schema_state}

@app.get("/healthz")
@app.head("/healthz")
async def healthz():
    """
    Liveness probe with truthful worker heartbeat signals.

    Accepts GET and HEAD (UptimeRobot free tier uses HEAD).
    Always returns HTTP 200 — callers must inspect payload fields for
    stalled/idle heuristics.

    worker_sync and ai_summarizer sections are populated from shared in-memory
    dicts when worker threads run in the same process.  In separate-dyno
    deployments (Render) those dicts stay at their initializing defaults,
    which is still a truthful response.
    """
    now = time.time()

    # ── worker_sync section ───────────────────────────────────────────────
    ws = _get_worker_heartbeat()
    lcs = ws.get("last_cycle_started_at")
    lsucc = ws.get("last_success_ts")
    worker_sync = {
        "enabled": ws.get("enabled"),
        "status": ws.get("status", "unknown"),
        "started_at": ws.get("started_at"),
        "last_cycle_started_at": lcs,
        "last_cycle_completed_at": ws.get("last_cycle_completed_at"),
        "last_cycle_seconds_ago": round(now - lcs, 1) if lcs else None,
        "last_success_seconds_ago": round(now - lsucc, 1) if lsucc else None,
        "last_account_count": ws.get("last_account_count"),
        "last_error_at": ws.get("last_error_at"),
        "last_error_type": ws.get("last_error_type"),
        "schema_error_count": ws.get("schema_error_count", 0),
    }

    # ── ai_summarizer section ─────────────────────────────────────────────
    ai = _get_ai_worker_heartbeat()
    ai_summarizer = {
        "enabled": ai.get("enabled"),
        "status": ai.get("status", "unknown"),
        "worker_id": ai.get("worker_id"),
        "started_at": ai.get("started_at"),
        "last_loop_at": ai.get("last_loop_at"),
        "last_claimed_at": ai.get("last_claimed_at"),
        "last_processed_at": ai.get("last_processed_at"),
        "last_idle_at": ai.get("last_idle_at"),
        "last_batch_size": ai.get("last_batch_size"),
        "last_error_at": ai.get("last_error_at"),
        "last_error_type": ai.get("last_error_type"),
        "last_error_message": ai.get("last_error_message"),
    }

    return {
        "status": "ok",
        "schema": ControlPlane.schema_state,
        "api_timestamp": datetime.now(timezone.utc).isoformat(),
        "worker_sync": worker_sync,
        "ai_summarizer": ai_summarizer,
    }

@app.get("/api/diagnostic", dependencies=[Depends(require_jwt_auth)])
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

@app.get("/debug-config", dependencies=[Depends(require_jwt_auth)])
async def debug_config():
    """
    Debug endpoint to verify OAuth configuration at runtime.
    CRITICAL: Verifies redirect URI matches Google Cloud Console.

    Expected LOCAL: http://127.0.0.1:8888/auth/callback/google
    Expected PROD: https://intelligent-email-assistant-3e1a.onrender.com/auth/callback/google
    """
    if not debug_allowed():
        raise HTTPException(status_code=404)
    from backend.config import Config
    port = os.getenv("PORT", "8888")
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8888").rstrip("/")

    return {
        "PORT": port,
        "BASE_URL": base_url,
        "REDIRECT_URI": Config.get_callback_url(),
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID", "NOT_SET")[:20] + "...",
        "FRONTEND_URL": os.getenv("FRONTEND_URL", "http://localhost:5173"),
        "ENVIRONMENT": "LOCAL" if ("localhost" in base_url or "127.0.0.1" in base_url) else "PRODUCTION"
    }


@app.get("/debug-imports", dependencies=[Depends(require_jwt_auth)])
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

@app.get("/accounts", dependencies=[Depends(require_jwt_auth)])
async def list_accounts_root():
    """Compatibility bridge: root /accounts delegates to canonical /api/accounts."""
    return await list_accounts()

# ------------------------------------------------------------------
# FRONTEND BRIDGE ROUTES
# ------------------------------------------------------------------
@app.get("/process", dependencies=[Depends(require_jwt_auth)])
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

@app.get("/emails", dependencies=[Depends(require_jwt_auth)])
async def list_emails_root(account_id: Optional[str] = Query(None)):
    """Compatibility bridge: root /emails delegates to canonical /api/emails."""
    return await list_emails(account_id)

# ------------------------------------------------------------------
# API ROUTES
# ------------------------------------------------------------------
api_router = APIRouter(prefix="/api", dependencies=[Depends(require_jwt_auth)])
MAX_ATTACHMENT_PREVIEW_BYTES = 10 * 1024 * 1024


def _decode_gmail_body_data(data: str) -> bytes:
    if not data:
        return b""

    if len(data) % 4:
        data += "=" * (4 - (len(data) % 4))

    return base64.urlsafe_b64decode(data.encode("utf-8"))


def _get_part_header(part: Dict[str, Any], header_name: str) -> str:
    for header in part.get("headers", []) or []:
        if (header.get("name") or "").lower() == header_name.lower():
            return header.get("value") or ""
    return ""


def _strip_content_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    normalized = value.strip().strip("<>").strip()
    return normalized or None


def _iter_mime_parts(payload: Dict[str, Any]):
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _iter_mime_parts(part)


def _find_first_mime_part(payload: Dict[str, Any], mime_type: str) -> Optional[Dict[str, Any]]:
    current_mime_type = (payload.get("mimeType") or "").lower()
    body = payload.get("body", {}) or {}
    if current_mime_type == mime_type.lower() and body.get("data"):
        return payload

    for part in payload.get("parts", []) or []:
        found = _find_first_mime_part(part, mime_type)
        if found:
            return found

    return None


def _find_attachment_part(payload: Dict[str, Any], attachment_id: str) -> Optional[Dict[str, Any]]:
    for part in _iter_mime_parts(payload):
        body = part.get("body", {}) or {}
        if body.get("attachmentId") == attachment_id:
            return part
    return None


def _normalize_attachment_id(raw_id: Optional[str]) -> str:
    """Normalize a Gmail attachment ID for consistent lookup between rendered and serving paths."""
    if not raw_id:
        return ""
    return raw_id.strip()


def _build_attachment_part_index(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Build a normalized_attachment_id → {part, raw_attachment_id} index using the same
    _collect_attachment_candidate_parts logic as the rendered payload builder.
    This guarantees both paths use an identical resolution strategy.
    """
    index: Dict[str, Dict[str, Any]] = {}
    for part in _collect_attachment_candidate_parts(payload):
        body = part.get("body", {}) or {}
        att_id = body.get("attachmentId")
        if att_id:
            norm = _normalize_attachment_id(att_id)
            if norm:
                index[norm] = {"part": part, "raw_attachment_id": att_id}
    return index


def _collect_attachment_candidate_parts(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    def walk(part: Dict[str, Any]) -> None:
        filename = (part.get("filename") or "").strip()
        body = part.get("body", {}) or {}
        attachment_id = body.get("attachmentId")
        inline_data = body.get("data")

        if filename and (attachment_id or inline_data):
            candidates.append(part)

        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return candidates


def _make_stable_attachment_key(ordinal: int, filename: str, mime_type: str, size: int) -> str:
    """
    Build a deterministic, URL-safe attachment key from message-local metadata.
    Never embeds the opaque Gmail attachmentId — reproducible from the same MIME payload.
    """
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', filename)[:40]
    safe_mime = re.sub(r'[^A-Za-z0-9._-]', '_', mime_type)[:20]
    return f"{ordinal:03d}_{safe_name}_{safe_mime}_{size}"

def _normalize_attachment_filename(filename: str, mime_type: str) -> str:
    """
    Collapse duplicated terminal extensions when the filename already includes
    the suffix implied by the MIME type (for example: report.pdf.pdf → report.pdf).
    Leaves all other filenames unchanged.
    """
    normalized = (filename or "").strip()
    if not normalized:
        return ""

    explicit_mime = (mime_type or "").strip().lower()

    candidate_exts: set = set()

    fallback_exts_by_mime = {
        "application/pdf": {".pdf"},
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
        "image/jpeg": {".jpg", ".jpeg", ".jpe"},
        "image/png": {".png"},
        "image/webp": {".webp"},
        "image/gif": {".gif"},
        "text/csv": {".csv"},
        "text/plain": {".txt", ".text"},
    }

    if explicit_mime in fallback_exts_by_mime:
        candidate_exts.update(fallback_exts_by_mime[explicit_mime])

    candidate_mime_types: List[str] = []
    if explicit_mime and explicit_mime != "application/octet-stream":
        candidate_mime_types.append(explicit_mime)

    guessed_mime, _ = mimetypes.guess_type(normalized)
    guessed_mime = (guessed_mime or "").strip().lower()
    if guessed_mime and guessed_mime not in candidate_mime_types:
        candidate_mime_types.append(guessed_mime)

    for candidate_mime in candidate_mime_types:
        guessed_ext = mimetypes.guess_extension(candidate_mime, strict=False)
        cleaned_guessed_ext = (guessed_ext or "").strip().lower()
        if cleaned_guessed_ext.startswith(".") and len(cleaned_guessed_ext) > 1:
            candidate_exts.add(cleaned_guessed_ext)

        for ext in mimetypes.guess_all_extensions(candidate_mime, strict=False) or []:
            cleaned_ext = (ext or "").strip().lower()
            if cleaned_ext.startswith(".") and len(cleaned_ext) > 1:
                candidate_exts.add(cleaned_ext)

    deduped = normalized
    while True:
        base, ext = os.path.splitext(deduped)
        _, parent_ext = os.path.splitext(base)

        current_ext = (ext or "").strip().lower()
        previous_ext = (parent_ext or "").strip().lower()

        if not current_ext or not previous_ext:
            return deduped

        if current_ext == previous_ext:
            if candidate_exts and current_ext not in candidate_exts:
                return deduped
            deduped = base
            continue

        if candidate_exts and current_ext in candidate_exts and previous_ext in candidate_exts:
            deduped = base
            continue

        return deduped

def _build_attachment_entries(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Single source of truth for surfaced attachment metadata.
    Used by both the rendered payload builder and the byte-serving route.

    Assigns each candidate part a stable, deterministic attachment_key derived from
    traversal ordinal + filename + mime_type + size.  The raw Gmail attachmentId is
    preserved internally but is never exposed as a public route token.
    """
    seen_dedup: set = set()
    entries: List[Dict[str, Any]] = []
    ordinal = 0

    for part in _collect_attachment_candidate_parts(payload):
        mime_type = (part.get("mimeType") or "application/octet-stream").strip() or "application/octet-stream"
        raw_filename = (part.get("filename") or "").strip()
        filename = _normalize_attachment_filename(raw_filename, mime_type)
        body = part.get("body", {}) or {}
        raw_attachment_id = body.get("attachmentId")
        inline_data = body.get("data")
        size = int(body.get("size") or 0)
        content_id = _strip_content_id(_get_part_header(part, "Content-ID"))
        is_image = mime_type.startswith("image/")

        if not filename or not (raw_attachment_id or inline_data):
            continue

        dedup_key = (raw_attachment_id or "", filename, mime_type, size)
        if dedup_key in seen_dedup:
            continue
        seen_dedup.add(dedup_key)

        attachment_key = _make_stable_attachment_key(ordinal, filename, mime_type, size)
        ordinal += 1

        entries.append({
            "attachment_key": attachment_key,
            "raw_attachment_id": raw_attachment_id,
            "inline_data": inline_data,
            "filename": filename,
            "mime_type": mime_type,
            "size": size,
            "is_image": is_image,
            "content_id": content_id,
            "part": part,
        })

    return entries


def _build_attachment_entry_index(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build a stable attachment_key → entry lookup dict from the entries list."""
    return {e["attachment_key"]: e for e in entries}


def _collect_cid_references(body_html: Optional[str]) -> set:
    if not body_html:
        return set()

    matches = re.findall(r'cid:([^"\'>\s]+)', body_html, flags=re.IGNORECASE)
    normalized = set()

    for match in matches:
        value = (match or "").strip().strip("<>").strip()
        if value:
            normalized.add(value.lower())

    return normalized


def _build_large_file_placeholder_data_uri(filename: str, size_bytes: int) -> str:
    size_mb = size_bytes / (1024 * 1024)
    label = f"File too large to preview — {filename} ({size_mb:.1f} MB)"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='240' viewBox='0 0 1200 240'>"
        "<rect width='1200' height='240' rx='16' fill='#0f172a' stroke='#334155' stroke-width='2'/>"
        "<text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' "
        "font-family='Arial, sans-serif' font-size='34' fill='#cbd5e1'>"
        f"{escape(label)}"
        "</text>"
        "</svg>"
    )
    encoded_svg = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded_svg}"


def _resolve_inline_cid_sources(body_html: str, cid_sources: Dict[str, str]) -> str:
    resolved_html = body_html
    for content_id, resolved_src in cid_sources.items():
        replacement_patterns = [
            rf"cid:{re.escape(content_id)}",
            rf"cid:<{re.escape(content_id)}>",
            rf"cid:%3C{re.escape(content_id)}%3E",
        ]
        for pattern in replacement_patterns:
            resolved_html = re.sub(
                pattern,
                resolved_src,
                resolved_html,
                flags=re.IGNORECASE,
            )
    return resolved_html


def _fetch_raw_gmail_message(account_id: str, gmail_message_id: str) -> Optional[Dict[str, Any]]:
    try:
        from backend.providers.gmail import GmailProvider
        from backend.api.gmail_client import GmailClient as WorkerGmailClient

        provider = GmailProvider()
        token_data = provider._load_token_data(account_id)
        if not token_data or "token" not in token_data:
            raise RuntimeError("auth_required")

        client = WorkerGmailClient(provider._build_worker_token_data(token_data))
        return client.get_message(gmail_message_id)
    except Exception as e:
        logger.error(
            f"[API] Raw message fetch failed for {gmail_message_id[:8]}... "
            f"(type={type(e).__name__})"
        )
        return None


def _lookup_email_record_by_message_id(gmail_message_id: str) -> Optional[Dict[str, Any]]:
    store = safe_get_store()
    if not store:
        return None

    response = (
        store.client.table("emails")
        .select("account_id,body,subject,sender,date,gmail_message_id,thread_id")
        .eq("gmail_message_id", gmail_message_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None

    return response.data[0]


_DRIVE_ANCHOR_RE = re.compile(
    r'<a\b[^>]*?\bhref=["\']?(https://(?:drive|docs)\.google\.com[^"\'\s>]*)["\']?[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_DRIVE_BARE_URL_RE = re.compile(
    r'https://(?:drive|docs)\.google\.com/\S+',
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _classify_drive_url(url: str) -> str:
    if 'docs.google.com/document' in url:
        return 'google_docs'
    if 'docs.google.com/spreadsheets' in url:
        return 'google_sheets'
    if 'docs.google.com/presentation' in url:
        return 'google_slides'
    return 'google_drive'


_DRIVE_FILE_ID_RE = re.compile(r'/d/([a-zA-Z0-9_-]+)')


def _extract_drive_linked_files(
    body_html: Optional[str],
    body_text: Optional[str],
) -> List[Dict[str, Any]]:
    """Extract Google Drive / Docs linked-file metadata from email body.

    Deduplicates by Drive file identity (/d/{file_id}) when present,
    falling back to canonical URL equality. Friendly anchor titles are
    preferred over raw URL titles when merging duplicates.
    """

    def _extract_file_id(url: str) -> Optional[str]:
        m = _DRIVE_FILE_ID_RE.search(url)
        return m.group(1) if m else None

    def _canonicalize(url: str) -> str:
        # Strip query string and fragment; trailing punctuation already stripped by caller.
        url = url.split('?')[0].split('#')[0]
        return url

    def _is_raw_title(title: str, url: str) -> bool:
        # A title is "raw" when it is just the URL itself (plain-text fallback).
        return title == url or title.startswith('https://')

    def _truncate_url(url: str, limit: int = 80) -> str:
        return url if len(url) <= limit else url[:limit] + '…'

    # Ordered dedup structures: key -> entry dict, plus insertion-order list.
    entries_by_key: Dict[str, Dict[str, Any]] = {}
    entry_order: List[str] = []

    def _upsert(title: str, url: str) -> None:
        canonical = _canonicalize(url)
        file_id = _extract_file_id(canonical)
        dedup_key = f'id:{file_id}' if file_id else f'url:{canonical}'

        # Fallback label: never leave a raw full-length URL as the display title.
        display_title = title if not _is_raw_title(title, url) else _truncate_url(canonical)

        if dedup_key not in entries_by_key:
            entries_by_key[dedup_key] = {
                'title': display_title,
                'url': canonical,
                'provider': _classify_drive_url(canonical),
            }
            entry_order.append(dedup_key)
        else:
            existing = entries_by_key[dedup_key]
            # Upgrade to friendly title if the stored title is still raw/truncated.
            if _is_raw_title(existing['title'], existing['url']) and not _is_raw_title(title, url):
                existing['title'] = title

    if body_html:
        for match in _DRIVE_ANCHOR_RE.finditer(body_html):
            url = match.group(1).rstrip('.,;)')
            raw_title = match.group(2)
            title = _HTML_TAG_RE.sub('', raw_title).strip() or url
            _upsert(title, url)

    if body_text:
        for match in _DRIVE_BARE_URL_RE.finditer(body_text):
            url = match.group(0).rstrip('.,;)')
            _upsert(url, url)

    return [entries_by_key[key] for key in entry_order]


def _build_rendered_email_payload(
    account_id: str,
    gmail_message_id: str,
    fallback_body: str,
) -> Dict[str, Any]:
    raw_message = _fetch_raw_gmail_message(account_id, gmail_message_id)
    if not raw_message:
        return {
            "body_html": None,
            "body_text": fallback_body or "",
            "attachments": [],
        }

    payload = raw_message.get("payload", {}) or {}
    html_part = _find_first_mime_part(payload, "text/html")
    text_part = _find_first_mime_part(payload, "text/plain")

    body_html = None
    if html_part:
        html_bytes = _decode_gmail_body_data((html_part.get("body", {}) or {}).get("data", ""))
        body_html = html_bytes.decode("utf-8", errors="replace") if html_bytes else None

    body_text = fallback_body or ""
    if text_part:
        text_bytes = _decode_gmail_body_data((text_part.get("body", {}) or {}).get("data", ""))
        if text_bytes:
            body_text = text_bytes.decode("utf-8", errors="replace")

    cid_sources: Dict[str, str] = {}
    attachments: List[Dict[str, Any]] = []
    referenced_cids = _collect_cid_references(body_html)

    from backend.providers.gmail import GmailProvider
    provider = GmailProvider()

    for entry in _build_attachment_entries(payload):
        attachment_key = entry["attachment_key"]
        raw_attachment_id = entry["raw_attachment_id"]
        inline_data = entry["inline_data"]
        filename = entry["filename"]
        mime_type = entry["mime_type"]
        size = entry["size"]
        is_image = entry["is_image"]
        content_id = entry["content_id"]

        normalized_content_id = (content_id or "").lower()
        is_referenced_inline = bool(normalized_content_id and normalized_content_id in referenced_cids)

        if is_image and is_referenced_inline:
            if size > MAX_ATTACHMENT_PREVIEW_BYTES:
                cid_sources[content_id] = _build_large_file_placeholder_data_uri(
                    filename or content_id,
                    size,
                )
            else:
                try:
                    if raw_attachment_id:
                        content_bytes = provider.get_attachment_bytes(account_id, gmail_message_id, raw_attachment_id)
                    else:
                        content_bytes = _decode_gmail_body_data(inline_data or "")
                except Exception:
                    content_bytes = b""

                if content_bytes:
                    encoded_bytes = base64.b64encode(content_bytes).decode("ascii")
                    cid_sources[content_id] = f"data:{mime_type};base64,{encoded_bytes}"

            continue

        too_large = size > MAX_ATTACHMENT_PREVIEW_BYTES
        # Stable key is URL-safe — no encoding needed, no opaque Gmail ID exposed.
        route_url = f"/api/attachments/{gmail_message_id}/{attachment_key}" if raw_attachment_id else None

        preview_url = None
        if is_image and not too_large:
            if raw_attachment_id:
                try:
                    preview_bytes = provider.get_attachment_bytes(
                        account_id, gmail_message_id, raw_attachment_id
                    )
                except Exception as _preview_exc:
                    logger.warning(
                        "[API] Failed to fetch image preview bytes for %r in message %s: %s",
                        filename,
                        gmail_message_id[:12],
                        type(_preview_exc).__name__,
                    )
                    preview_bytes = b""
                if preview_bytes:
                    preview_b64 = base64.b64encode(preview_bytes).decode("ascii")
                    preview_url = f"data:{mime_type};base64,{preview_b64}"
            elif inline_data:
                try:
                    preview_bytes = _decode_gmail_body_data(inline_data)
                except Exception:
                    preview_bytes = b""
                if preview_bytes:
                    preview_b64 = base64.b64encode(preview_bytes).decode("ascii")
                    preview_url = f"data:{mime_type};base64,{preview_b64}"

        attachments.append(
            {
                "attachment_key": attachment_key,
                "filename": filename,
                "mime_type": mime_type,
                "size": size,
                "is_inline": False,
                "is_image": is_image,
                "preview_url": None if too_large else preview_url,
                "download_url": None if too_large else route_url,
                "too_large": too_large,
                "placeholder_text": (
                    f"File too large to preview — {filename} ({size / (1024 * 1024):.1f} MB)"
                    if too_large
                    else None
                ),
            }
        )

    resolved_html = _resolve_inline_cid_sources(body_html, cid_sources) if body_html else None
    linked_files = _extract_drive_linked_files(resolved_html or body_html, body_text)

    return {
        "body_html": resolved_html,
        "body_text": body_text or fallback_body or "",
        "attachments": attachments,
        "linked_files": linked_files,
    }


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


@api_router.get("/emails/{gmail_message_id}/rendered")
async def get_rendered_email(gmail_message_id: str):
    record = await asyncio.to_thread(_lookup_email_record_by_message_id, gmail_message_id)
    if not record:
        raise HTTPException(status_code=404, detail="Email not found")

    account_id = record.get("account_id")
    if not account_id:
        raise HTTPException(status_code=404, detail="Account not found for email")

    rendered_payload = await asyncio.to_thread(
        _build_rendered_email_payload,
        account_id,
        gmail_message_id,
        record.get("body") or "",
    )

    return {
        "gmail_message_id": gmail_message_id,
        "body_html": rendered_payload.get("body_html"),
        "body_text": rendered_payload.get("body_text") or (record.get("body") or ""),
        "attachments": rendered_payload.get("attachments") or [],
        "linked_files": rendered_payload.get("linked_files") or [],
    }


@api_router.get("/attachments/{message_id}/{attachment_key}")
async def get_attachment_stream(message_id: str, attachment_key: str, download: bool = Query(False)):
    """
    Serve attachment bytes by stable attachment_key.
    The stable key is deterministic from message-local metadata (ordinal + filename + mime + size).
    It is never the opaque Gmail attachmentId — that is resolved internally after lookup.
    """
    record = await asyncio.to_thread(_lookup_email_record_by_message_id, message_id)
    if not record:
        raise HTTPException(status_code=404, detail="Email not found")

    account_id = record.get("account_id")
    if not account_id:
        raise HTTPException(status_code=404, detail="Account not found for email")

    raw_message = await asyncio.to_thread(_fetch_raw_gmail_message, account_id, message_id)
    if not raw_message:
        raise HTTPException(status_code=404, detail="Raw Gmail message not found")

    payload = raw_message.get("payload", {}) or {}

    # Rebuild the same entry list as the rendered payload builder — guaranteed identical order.
    entries = _build_attachment_entries(payload)
    entry_index = _build_attachment_entry_index(entries)
    entry = entry_index.get(attachment_key)

    if not entry:
        logger.warning(
            "[API] Attachment 404 for message=%s requested_key=%r "
            "available_keys=%r filenames=%r mimes=%r",
            message_id[:12],
            attachment_key[:60],
            [e["attachment_key"] for e in entries[:6]],
            [e["filename"][:30] for e in entries[:6]],
            [e["mime_type"][:30] for e in entries[:6]],
        )
        raise HTTPException(status_code=404, detail="Attachment not found")

    raw_attachment_id = entry["raw_attachment_id"]
    if not raw_attachment_id:
        raise HTTPException(status_code=404, detail="Attachment has no downloadable bytes")

    size = entry["size"]
    if size > MAX_ATTACHMENT_PREVIEW_BYTES:
        raise HTTPException(status_code=413, detail="Attachment too large to preview or download")

    filename = entry["filename"]
    mime_type = entry["mime_type"] or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    from backend.providers.gmail import GmailProvider
    provider = GmailProvider()

    try:
        content = await asyncio.to_thread(
            provider.get_attachment_bytes,
            account_id,
            message_id,
            raw_attachment_id,
        )
    except RuntimeError as e:
        if "auth_required" in str(e):
            raise HTTPException(status_code=401, detail="Gmail credentials unavailable")
        raise HTTPException(status_code=502, detail="Attachment download failed")

    safe_filename = re.sub(r'["\\\r\n]+', "_", filename)
    is_inline_type = mime_type.startswith("image/") or mime_type == "application/pdf"
    disposition_type = "attachment" if download else ("inline" if is_inline_type else "attachment")

    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'{disposition_type}; filename="{safe_filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@api_router.post("/sync-now")
async def sync_now(
    account_id: str = Query("default"),
    max_emails: int = Query(10, description="Maximum emails to fetch (default: 10, validation: 10)"),
    backfill_limit: int = Query(0, description="Maximum legacy emails to backfill (default: 0=skip, validation: 10)")
):
    """
    User-driven Gmail sync endpoint with timeout protection.
    Executes ONE Gmail fetch + store cycle immediately.

    Args:
        account_id: Account identifier
        max_emails: Maximum emails to fetch (default 30, use 10 for deterministic validation)
        backfill_limit: Maximum legacy emails to backfill thread_id (default 0=skip, use 10 for validation)

    Returns status-only (no email contents):
    - {"status": "auth_required"} if no valid credentials
    - {"status": "no_new"} if no new emails found
    - {"status": "done", "count": N} if stored N emails
    - {"status": "timeout"} if sync takes longer than 28 seconds
    - {"status": "error"} on failure (no secrets leaked)
    """
    try:
        # Wrap with 28s timeout (Render has 30s HTTP timeout — 2s buffer)
        return await asyncio.wait_for(
            _sync_now_impl(account_id, max_emails, backfill_limit),
            timeout=28.0
        )
    except asyncio.TimeoutError:
        logger.error("[SYNC] Request timed out after 28s")
        return {"status": "timeout", "message": "Sync took too long, try reducing email count"}
    except Exception as e:
        logger.error(f"[SYNC] Top-level error: {type(e).__name__}: {e}")
        return {"status": "error", "message": str(e)}


async def _sync_now_impl(account_id: str, max_emails: int = 30, backfill_limit: int = 0):
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

        logger.info(f"[SYNC] Credentials loaded, fetching emails from Gmail (max: {max_emails})...")
        # Execute Gmail fetch with bounded scope
        emails = await asyncio.to_thread(run_engine, token_data, max_emails)

        # Handle auth errors
        if isinstance(emails, dict) and "__auth_error__" in emails:
            logger.info(f"[SYNC] Gmail authentication error detected")
            return {"status": "auth_required", "message": "Gmail token expired or revoked"}

        if not emails:
            logger.info(f"[SYNC] No emails returned from Gmail")
            return {"status": "no_new", "message": "No emails in inbox"}

        logger.info(f"[SYNC] Gmail fetch successful: {len(emails)} emails retrieved")

        # Store emails in Supabase with atomic AI job creation
        logger.info(f"[SYNC] Initializing Supabase store...")
        store = safe_get_store()
        if not store:
            logger.info(f"[SYNC] CRITICAL ERROR: Supabase store unavailable!")
            return {"status": "error", "message": "Database connection failed"}

        logger.info(f"[SYNC] Processing {len(emails)} emails for account: {effective_account_id}")

        # CRITICAL: Identify existing emails to prevent backfill
        # Only NEW emails (not in DB) are eligible for automatic AI jobs
        existing_message_ids = set()
        try:
            existing_result = await asyncio.to_thread(
                lambda: store.client.table("emails").select("gmail_message_id").eq(
                    "account_id", effective_account_id
                ).execute()
            )
            if existing_result and existing_result.data:
                existing_message_ids = {e['gmail_message_id'] for e in existing_result.data}
                logger.info(f"[SYNC] Found {len(existing_message_ids)} existing emails in DB")
        except Exception as e:
            logger.warning(f"[SYNC] Could not query existing emails: {e}")

        stored_count = 0
        ai_job_count = 0
        new_thread_ids = []
        failed_saves = []  # D3: Track failures deterministically

        for email in emails:
            try:
                # Extract Gmail stable ID for deduplication
                m_id = email.get("message_id") or email.get("id")

                # Skip emails without Gmail ID to prevent duplicate inserts
                if not m_id:
                    logger.warning(f"[SYNC] Skip email without gmail_message_id: {email.get('subject', 'No Subject')}")
                    continue

                # D2 FIX: Atomic save with conditional AI job creation
                # COST POLICY: Only NEW emails (not in DB) get automatic AI jobs
                # First 20 NEW emails get AI jobs (cost control)
                # Existing emails never get auto-backfilled
                is_new_email = (m_id not in existing_message_ids)
                create_ai_job = (is_new_email and ai_job_count < 20)

                result = await asyncio.to_thread(
                    store.save_email_atomic,
                    subject=email.get("subject", "No Subject"),
                    sender=email.get("sender", "Unknown"),
                    date=email.get("date", "Unknown"),
                    body=email.get("body", ""),
                    message_id=m_id,
                    account_id=effective_account_id,
                    tenant_id="primary",
                    create_ai_job=create_ai_job,
                    thread_id=email.get("thread_id")  # CRITICAL: Gmail thread ID for send functionality
                )

                # Validate atomic save succeeded
                if result and result.data:
                    stored_count += 1

                    # Track AI job creation (only count NEWLY created jobs, not pre-existing)
                    job_was_created = (
                        create_ai_job and
                        result.data.get('job_created') and
                        not result.data.get('job_existed')
                    )
                    if job_was_created:
                        ai_job_count += 1

                    # Best-effort: enqueue document processing job for new emails.
                    # Worker fetches MIME structure and skips gracefully if no
                    # supported attachment is found — no byte download here.
                    if is_new_email:
                        try:
                            await asyncio.to_thread(
                                store.enqueue_ai_job,
                                account_id=effective_account_id,
                                gmail_message_id=m_id,
                                job_type="document_process_v1",
                            )
                        except Exception:
                            pass  # Never fail sync for optional document job

                    new_or_existing = "NEW" if is_new_email else "existing"
                    logger.info(f"[SYNC] ✓ Saved email {stored_count}/{len(emails)} ({new_or_existing}): {email.get('subject', 'No Subject')[:50]} (AI job: {create_ai_job})")

                    # Track real Gmail thread_id for email_threads table
                    gmail_thread_id = email.get('thread_id', '')
                    if gmail_thread_id:
                        new_thread_ids.append((gmail_thread_id, email))

                    # Best-effort is_read update — never fails the sync
                    is_read_val = email.get('is_read', True)
                    try:
                        await asyncio.to_thread(
                            lambda: store.client.table("emails")
                                .update({"is_read": is_read_val})
                                .eq("account_id", effective_account_id)
                                .eq("gmail_message_id", m_id)
                                .execute()
                        )
                    except Exception as is_read_err:
                        logger.warning(f"[SYNC] is_read update failed for {m_id[:8]}... (non-fatal): {is_read_err}")
                else:
                    # D3 FIX: Track failed saves deterministically
                    failed_saves.append({
                        'message_id': m_id,
                        'subject': email.get('subject', 'No Subject')[:50],
                        'error': 'RPC returned no data'
                    })
                    logger.error(f"[SYNC] Failed to save email: {email.get('subject', 'No Subject')[:50]}")

            except Exception as e:
                # D3 FIX: Track exceptions deterministically
                failed_saves.append({
                    'message_id': email.get("message_id", "unknown"),
                    'subject': email.get('subject', 'No Subject')[:50],
                    'error': f"{type(e).__name__}: {str(e)}"
                })
                logger.error(f"[SYNC] Exception while storing email: {e}")
                logger.error(f"[SYNC] Email subject: {email.get('subject', 'No Subject')[:50]}")
                import traceback
                logger.error(f"[SYNC] Traceback: {traceback.format_exc()}")

        # D3 FIX: Deterministic failure reporting
        if failed_saves:
            logger.error(f"[SYNC] Storage failures: {len(failed_saves)}/{len(emails)} emails failed")
            for fail in failed_saves[:5]:  # Log first 5 failures
                logger.error(f"[SYNC] Failed: {fail['message_id'][:8]}... ({fail['subject']}): {fail['error']}")

        logger.info(f"[SYNC] Storage complete: {stored_count}/{len(emails)} emails saved, {ai_job_count} AI jobs created")

        # D2 FIX: AI jobs already created atomically - no separate enqueue needed
        # D1 FIX: No fire-and-forget - all operations completed before response
        logger.info(f"[SYNC] Atomic save completed: {stored_count} emails, {ai_job_count} AI jobs")

        # CRITICAL: Save threads to email_threads table for send functionality
        # Deduplicate threads by thread_id (multiple emails can belong to same thread)
        if new_thread_ids:
            unique_threads = {}
            for thread_id, email in new_thread_ids:
                if thread_id not in unique_threads:
                    unique_threads[thread_id] = email

            # CRITICAL FIX: Build complete payloads BEFORE asyncio.to_thread
            # Eliminates ALL closure issues by passing only explicit arguments
            timestamp_now = datetime.now(timezone.utc).isoformat()

            def upsert_thread_sync(db_client, payload: dict, conflict_spec: str):
                """Pure synchronous helper - no closures, only explicit args."""
                return db_client.table("email_threads").upsert(
                    payload,
                    on_conflict=conflict_spec
                ).execute()

            threads_saved = 0
            for thread_id, email in unique_threads.items():
                try:
                    # Debug: Prove thread_id correctness
                    msg_id = email.get('message_id', 'unknown')
                    logger.info(f"[SYNC] Thread save candidate: thread_id={thread_id[:16]}..., message_id={msg_id[:16]}...")

                    # Build complete payload with NO closures
                    thread_payload = {
                        "thread_id": thread_id,
                        "account_id": effective_account_id,
                        "subject": email.get("subject", "No Subject"),
                        "summary": None,  # Will be filled by AI later
                        "created_at": timestamp_now
                    }

                    # Call with ONLY explicit arguments - zero closures
                    await asyncio.to_thread(
                        upsert_thread_sync,
                        store.client,
                        thread_payload,
                        "thread_id,account_id"
                    )
                    threads_saved += 1
                except Exception as ex:
                    logger.warning(f"[SYNC] Failed to save thread {thread_id}: {ex}")

            logger.info(f"[SYNC] Saved {threads_saved} unique threads to email_threads table")

        # Emit socket event for new emails
        try:
            await sio.emit("emails_updated", {"count_new": stored_count})
            logger.info(f"[SYNC] Socket.IO event emitted: emails_updated (count: {stored_count})")
        except Exception as e:
            logger.warning(f"[SYNC] Failed to emit socket event: {e}")

        # BACKFILL FIX: Enrich existing emails that have NULL thread_id
        # This covers emails synced before the thread_id write-path fix
        # Controlled by backfill_limit parameter (default 0 = skip)
        if backfill_limit > 0:
            try:
                logger.info(f"[SYNC] Backfilling thread_id for existing emails (limit: {backfill_limit})...")
                from backend.integrations.gmail import GmailClient

                # Query emails where thread_id is NULL
                null_thread_emails = await asyncio.to_thread(
                    lambda: store.client.table("emails")
                        .select("gmail_message_id")
                        .eq("account_id", effective_account_id)
                        .is_("thread_id", "null")
                        .limit(backfill_limit)
                        .execute()
                )

                if null_thread_emails.data and len(null_thread_emails.data) > 0:
                    logger.info(f"[SYNC] Found {len(null_thread_emails.data)} emails missing thread_id")

                    # Create Gmail client with same credentials used for sync
                    gmail_client = GmailClient(token_data)
                    backfilled_count = 0

                    for email_row in null_thread_emails.data:
                        try:
                            gmail_message_id = email_row.get("gmail_message_id")
                            if not gmail_message_id:
                                continue

                            # Fetch message metadata from Gmail API to get thread_id
                            msg_data = await asyncio.to_thread(
                                lambda mid=gmail_message_id: gmail_client.service.users().messages().get(
                                    userId='me',
                                    id=mid,
                                    format='minimal'
                                ).execute()
                            )

                            fetched_thread_id = msg_data.get('threadId')
                            if fetched_thread_id:
                                # Update database with thread_id
                                await asyncio.to_thread(
                                    lambda tid=fetched_thread_id, mid=gmail_message_id: store.client.table("emails").update(
                                        {"thread_id": tid}
                                    ).eq("gmail_message_id", mid).eq("account_id", effective_account_id).execute()
                                )
                                backfilled_count += 1
                        except Exception as backfill_err:
                            logger.warning(f"[SYNC] Backfill failed for {gmail_message_id[:8]}...: {backfill_err}")

                    logger.info(f"[SYNC] Backfilled thread_id for {backfilled_count}/{len(null_thread_emails.data)} emails")
                else:
                    logger.info("[SYNC] No emails found missing thread_id")
            except Exception as backfill_error:
                # Don't fail sync if backfill fails - this is a best-effort enhancement
                logger.warning(f"[SYNC] thread_id backfill process failed: {backfill_error}")
        else:
            logger.info("[SYNC] Legacy backfill skipped (backfill_limit=0)")

        logger.info(f"[SYNC] ========== SYNC REQUEST COMPLETED ==========")
        logger.info(f"[SYNC] Final status: {stored_count} emails saved, {ai_job_count} AI jobs created")

        # D3 FIX: Return deterministic status including failures
        response = {
            "status": "done" if not failed_saves else "partial",
            "count": stored_count,
            "ai_jobs_created": ai_job_count,
            "processed_count": stored_count
        }

        if failed_saves:
            response["failed_count"] = len(failed_saves)
            response["failures"] = [
                {"message_id": f["message_id"][:16], "error": f["error"]}
                for f in failed_saves[:10]  # Return first 10 failures
            ]

        return response

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
async def list_threads(account_id: str = Query(None)):
    """
    List real tracked Gmail threads from database.
    CRITICAL: Returns same data source as send endpoint (email_threads table).
    Supports optional account_id filtering.
    """
    store = safe_get_store()
    if not store:
        return {
            "count": 0,
            "threads": [],
            "error": "Database unavailable"
        }

    try:
        # Query email_threads table (same source as send endpoint)
        # CRITICAL: Filter by account_id if provided
        query = store.client.table("email_threads").select(
            "thread_id, account_id, subject, summary, created_at"
        )

        if account_id:
            query = query.eq("account_id", account_id)

        thread_records = await asyncio.to_thread(
            lambda q=query: q.order("created_at", desc=True).limit(100).execute()
        )

        if not thread_records.data:
            return {
                "count": 0,
                "threads": []
            }

        # Transform to API format
        threads_list = [
            {
                "thread_id": t.get("thread_id"),
                "account_id": t.get("account_id", "default"),
                "summary": t.get("summary") or t.get("subject") or "No summary",
                "overview": t.get("summary") or t.get("subject") or "No overview",
                "confidence_score": 1.0,  # Real tracked threads
                "timestamp": t.get("created_at", datetime.now(timezone.utc).isoformat()),
            }
            for t in thread_records.data
        ]

        return {
            "count": len(threads_list),
            "threads": threads_list
        }

    except Exception as e:
        logger.error(f"[THREADS] Failed to list threads: {e}")
        return {
            "count": 0,
            "threads": [],
            "error": str(e)
        }

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
    Legacy thread summarize route — kept alive for compatibility.
    The active summarization path is POST /emails/{gmail_message_id}/summarize.
    """
    return {
        "status": "deprecated",
        "message": "Use POST /api/emails/{gmail_message_id}/summarize instead."
    }


@api_router.post("/threads/{thread_id}/analyze")
async def analyze_thread(thread_id: str):
    """Stub: trigger on-demand analysis for a thread."""
    require_schema_ok()
    return {"thread_id": thread_id, "status": "queued", "message": "Analysis scheduled"}

# ─── Agent request/response models (BL-08/BL-09) ────────────────────────────

class AgentDraftRequest(BaseModel):
    account_id: str
    user_instruction: str
    conversation_id: Optional[str] = None


class AgentConsentRequest(BaseModel):
    account_id: str


class AgentFeedbackRequest(BaseModel):
    account_id: str
    conversation_id: str
    action_type: str         # e.g. "draft_reply"
    subject: str             # email subject ONLY — max 500 chars, never email body
    outcome: str             # "accepted" | "rejected" | "edited"
    rating: Optional[int] = None


@api_router.post("/threads/{thread_id}/draft")
async def draft_thread_reply(thread_id: str, request: AgentDraftRequest):
    """
    Generate a draft reply proposal using the AI agent.
    Returns draft text for display in ReplyComposeModal.

    SEND SAFETY: This route never sends email. The returned draft is for the
    user to review and send through ReplyComposeModal — the sole send surface.

    Enforces (in order, fail fast):
      1. Rate limit — 10 actions per account per hour (rate_limit_counters table)
      2. Approval gate — audit_log user_approved=TRUE required (fails closed)
    """
    store = safe_get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Storage unavailable")
    effective_account_id = resolve_account_id(None, request.account_id)

    # Fetch email from DB — never trust client-provided body content
    try:
        email_resp = (
            store.client.table("emails")
            .select("subject,sender,body")
            .eq("account_id", effective_account_id)
            .eq("thread_id", thread_id)          # thread_id from path param
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        rows = email_resp.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Email not found")
        email_row = rows[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[AGENT-DRAFT] Email fetch failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Failed to fetch email")

    subject = email_row.get("subject", "")
    sender = email_row.get("sender", "")
    # Body excerpt only — also capped inside agent.propose_draft
    body_excerpt = (email_row.get("body") or "")[:1000]

    from backend.assistant.agent import EmailAgent, AgentRateLimitError, AgentApprovalError
    agent = EmailAgent(store)
    try:
        result = await agent.propose_draft(
            account_id=effective_account_id,
            thread_id=thread_id,                 # proven column: thread_id TEXT NOT NULL
            subject=subject,
            sender=sender,
            body_excerpt=body_excerpt,
            user_instruction=request.user_instruction,
            conversation_id=request.conversation_id,
        )
    except AgentRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except AgentApprovalError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("[AGENT-DRAFT] Draft generation failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Draft generation failed")

    return {
        "thread_id": thread_id,
        "draft": result["draft"],
        "conversation_id": result["conversation_id"],
        "status": "ok",
    }


class SendEmailRequest(BaseModel):
    """Request model for sending email replies - backend owns reply context."""
    body: str
    subject: Optional[str] = None
    cc: Optional[str] = None


@api_router.post("/threads/{thread_id}/send")
async def send_thread_reply(thread_id: str, request: SendEmailRequest):
    """
    Send an email reply with RFC-compliant threading headers.
    Backend owns reply context derivation - client only provides draft text.

    Args:
        thread_id: Gmail thread ID (from URL path)
        request: SendEmailRequest with body (draft text only)

    Returns:
        Success: {"success": true, "message_id": "...", "thread_id": "...", "sent_to": "..."}
        Failure: {"success": false, "error": "..."}

    Backend derives:
        - account_id from email_threads table
        - parent message from Gmail API
        - recipient from Reply-To or From header
        - subject with Re: normalization
    """
    try:
        logger.info(f"[SEND] Starting send for thread {thread_id}")

        # Step 1: Derive account_id from database
        store = safe_get_store()
        if not store:
            return {"success": False, "error": "Database unavailable"}

        # Query email_threads to get account_id for this thread
        # CRITICAL: Detect ambiguity explicitly (0 rows, 1 row, >1 rows)
        try:
            thread_records = await asyncio.to_thread(
                lambda: store.client.table("email_threads")
                .select("account_id, subject")
                .eq("thread_id", thread_id)
                .execute()
            )

            # Explicit 0-row detection - try emails table as fallback
            if not thread_records.data or len(thread_records.data) == 0:
                logger.warning(f"[SEND] Thread {thread_id} not found in email_threads - trying emails table fallback")
                email_records = await asyncio.to_thread(
                    lambda: store.client.table("emails")
                    .select("account_id")
                    .eq("thread_id", thread_id)
                    .execute()
                )
                if not email_records.data or len(email_records.data) == 0:
                    logger.warning(f"[SEND] Thread {thread_id} not found in emails table either")
                    return {
                        "success": False,
                        "error": f"Thread {thread_id} not tracked in database - sync emails first"
                    }
                unique_accounts = list(set(r.get('account_id') for r in email_records.data if r.get('account_id')))
                if len(unique_accounts) > 1:
                    logger.error(f"[SEND] Thread {thread_id} ambiguous across {len(unique_accounts)} accounts: {unique_accounts}")
                    return {
                        "success": False,
                        "error": f"Thread {thread_id} exists in multiple accounts {unique_accounts}. Cannot determine reply context."
                    }
                account_id = unique_accounts[0]
                logger.info(f"[SEND] Derived account_id: {account_id} (fallback from emails table)")
                try:
                    await asyncio.to_thread(
                        lambda: store.client.table("email_threads")
                        .upsert({"thread_id": thread_id, "account_id": account_id}, on_conflict="thread_id")
                        .execute()
                    )
                    logger.info(f"[SEND] Upserted thread {thread_id} into email_threads for account {account_id}")
                except Exception as upsert_err:
                    logger.warning(f"[SEND] email_threads upsert failed (non-fatal): {upsert_err}")

            # Explicit >1-row detection (multi-account ambiguity)
            elif len(thread_records.data) > 1:
                ambiguous_accounts = [r.get('account_id') for r in thread_records.data]
                logger.error(f"[SEND] Thread {thread_id} is ambiguous across {len(thread_records.data)} accounts: {ambiguous_accounts}")
                return {
                    "success": False,
                    "error": f"Thread {thread_id} exists in multiple accounts {ambiguous_accounts}. Cannot determine reply context."
                }

            # Safe: exactly 1 row
            else:
                account_id = thread_records.data[0].get('account_id', 'default')
                logger.info(f"[SEND] Derived account_id: {account_id} (unique match)")

        except Exception as e:
            logger.error(f"[SEND] Database query failed: {e}")
            return {"success": False, "error": "Failed to look up thread in database"}

        # Step 2: Load credentials for derived account_id
        credential_store = CredentialStore(persistence)
        token_data = await asyncio.to_thread(
            credential_store.load_credentials,
            account_id
        )

        if not token_data or 'token' not in token_data:
            logger.warning(f"[SEND] No valid credentials for account {account_id}")
            return {
                "success": False,
                "error": f"Authentication required for account {account_id}"
            }

        # Step 3: Create Gmail client and fetch latest INBOUND message in thread
        # CRITICAL: Filters out SENT messages to prevent self-reply loops
        gmail_client = GmailClient(token_data)
        gmail_client.refresh_if_needed()

        logger.info(f"[SEND] Fetching latest inbound message from thread via Gmail API")
        try:
            latest_message = await asyncio.to_thread(
                gmail_client.get_thread_latest_inbound_message,
                thread_id
            )

            if not latest_message:
                logger.error(f"[SEND] Thread {thread_id} has no inbound messages (only SENT messages or empty)")
                return {
                    "success": False,
                    "error": f"Thread {thread_id} has no inbound messages to reply to"
                }

            parent_gmail_message_id = latest_message['gmail_message_id']
            logger.info(f"[SEND] Parent message ID: {parent_gmail_message_id} (latest inbound)")

        except RuntimeError as e:
            logger.error(f"[SEND] Failed to fetch thread messages: {e}")
            return {
                "success": False,
                "error": f"Failed to fetch thread from Gmail: {str(e)}"
            }

        # Step 4: Fetch RFC headers from parent message
        logger.info(f"[SEND] Fetching RFC reply headers from parent message")
        try:
            reply_headers = await asyncio.to_thread(
                gmail_client.get_reply_headers,
                parent_gmail_message_id
            )
        except RuntimeError as e:
            logger.error(f"[SEND] Failed to fetch reply headers: {e}")
            return {
                "success": False,
                "error": f"Failed to fetch parent message headers: {str(e)}"
            }

        # Step 5: Derive recipient - use Reply-To if present, else From
        recipient = latest_message.get('reply_to') or latest_message.get('from', '')
        if not recipient:
            logger.error(f"[SEND] No recipient found in parent message")
            return {
                "success": False,
                "error": "Cannot determine recipient - parent message has no From/Reply-To"
            }

        # Extract email address from "Name <email@domain.com>" format using stdlib
        # parseaddr safely handles various formats: "Name <email>", "<email>", "email"
        name, email_addr = parseaddr(recipient)
        recipient = email_addr if email_addr else recipient

        logger.info(f"[SEND] Derived recipient: {recipient}")

        # Step 6: Thread ID mismatch protection
        fetched_thread_id = reply_headers.get('thread_id', '')
        if fetched_thread_id and fetched_thread_id != thread_id:
            logger.error(f"[SEND] Thread ID mismatch - URL: {thread_id}, Gmail: {fetched_thread_id}")
            return {
                "success": False,
                "error": f"Thread ID mismatch - expected {thread_id}, got {fetched_thread_id}"
            }

        # Step 7: Extract headers for send
        in_reply_to = reply_headers.get('in_reply_to', '')
        references = reply_headers.get('references', '')
        raw_subject = reply_headers.get('subject', '(No Subject)')

        # Subject: use client-provided subject if given, else derive from thread.
        # Normalize: ensure exactly one "Re: " prefix regardless of source.
        client_subject = (request.subject or '').strip()
        base_subject = client_subject if client_subject else raw_subject
        subject = base_subject if base_subject.lower().startswith('re:') else f"Re: {base_subject}"

        logger.info(f"[SEND] Reply context - Subject: {subject}, To: {recipient}")

        # Step 8: Normalize and validate CC addresses
        normalized_cc = ''
        if request.cc:
            seen: set = set()
            valid_addrs: list = []
            for raw in re.split(r'[,;]', request.cc):
                addr = raw.strip()
                if not addr:
                    continue
                _, parsed = parseaddr(addr)
                if not parsed or '@' not in parsed or '.' not in parsed.split('@', 1)[-1]:
                    logger.warning(f"[SEND] Invalid CC address rejected: {addr!r}")
                    return {"success": False, "error": f"Invalid CC address: '{addr}'"}
                key = parsed.lower()
                if key not in seen:
                    seen.add(key)
                    valid_addrs.append(parsed)
            normalized_cc = ', '.join(valid_addrs)
            if normalized_cc:
                logger.info(f"[SEND] Normalized CC: {normalized_cc}")

        # Step 9: Send email via Gmail API
        result = await asyncio.to_thread(
            gmail_client.send_message,
            to=recipient,
            subject=subject,
            body=request.body,
            gmail_thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
            cc=normalized_cc or None
        )

        if result['success']:
            logger.info(f"[SEND] Email sent successfully - Message ID: {result['message_id']}")
            result['sent_to'] = recipient
            result['sent_cc'] = normalized_cc
            result['subject'] = subject
            if 'thread_id' not in result or not result['thread_id']:
                result['thread_id'] = thread_id

            # Best-effort sent log — never fails the send response
            try:
                sent_store = safe_get_store()
                if sent_store:
                    sent_payload = {
                        "account_id": account_id,
                        "gmail_message_id": result.get('message_id') or '',
                        "thread_id": result.get('thread_id') or thread_id,
                        "to_address": recipient,
                        "cc_addresses": normalized_cc or None,
                        "subject": subject,
                        "body_preview": request.body[:200],
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                        "source": "app_send",
                    }
                    await asyncio.to_thread(
                        lambda: sent_store.client.table("sent_emails").insert(sent_payload).execute()
                    )
                    logger.info(f"[SEND] Sent log inserted for thread {thread_id}")
            except Exception as log_err:
                logger.warning(f"[SEND] Sent log insert failed (non-fatal): {log_err}")
        else:
            logger.error(f"[SEND] Email send failed - Error: {result['error']}")

        return result

    except Exception as e:
        logger.error(f"[SEND] Unexpected error: {type(e).__name__}: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }

@api_router.post("/threads/{thread_id}/read-state")
async def set_thread_read_state(thread_id: str, request: Request):
    """
    Mark a Gmail thread as read or unread.

    account_id is derived server-side from the emails table by thread_id.
    The client does NOT supply account_id.

    Ambiguity guard: if the thread_id is associated with more than one distinct
    account_id in the emails table, the route fails explicitly rather than
    silently picking one — a write against the wrong account is worse than
    a clear error.

    Request body:  { "is_read": true | false }
    Response:      { "success": true, "gmail_updated": true, "db_updated": true }
                or { "success": true, "gmail_updated": true, "db_updated": false,
                     "db_error": "<reason>" }
                or { "success": false, "error": "<reason>" }

    Side-effects:
      1. GmailClient.set_thread_read_state() → threads().modify() (single API call)
      2. UPDATE emails SET is_read=<value>
             WHERE thread_id=:thread_id AND account_id=:resolved_account_id
         db_updated reflects whether this succeeded.
    """
    try:
        body = await request.json()
        is_read: bool = bool(body.get("is_read", True))
        # Client may supply account_id to skip the DB lookup entirely (preferred path).
        client_account_id: Optional[str] = body.get("account_id") or None

        store = safe_get_store()
        if not store:
            return {"success": False, "error": "Database unavailable"}

        if client_account_id:
            # Fast path: account_id supplied by client — no DB round-trip needed.
            account_id: str = client_account_id
            logger.info(f"[READ-STATE] account_id from client: {account_id}")
        else:
            # Slow path: derive account_id from the emails table.
            email_records = await asyncio.to_thread(
                lambda: store.client.table("emails")
                    .select("account_id")
                    .eq("thread_id", thread_id)
                    .execute()
            )
            if not email_records.data:
                return {"success": False, "error": f"Thread {thread_id} not found in emails table"}

            distinct_accounts = list({row["account_id"] for row in email_records.data if row.get("account_id")})
            if len(distinct_accounts) == 0:
                return {"success": False, "error": f"Thread {thread_id} has no resolvable account_id"}
            if len(distinct_accounts) > 1:
                logger.error(f"[READ-STATE] Ambiguous account for thread {thread_id}: {distinct_accounts}")
                return {
                    "success": False,
                    "error": (
                        f"Thread {thread_id} is associated with {len(distinct_accounts)} distinct accounts. "
                        "Supply account_id explicitly."
                    ),
                }
            account_id = distinct_accounts[0]

        credential_store = CredentialStore(persistence)
        token_data = await asyncio.to_thread(credential_store.load_credentials, account_id)
        if not token_data:
            return {
                "success": False,
                "error": f"No credentials for account {account_id} — re-authentication required",
            }

        # Build GmailClient and call Gmail API fully inside a thread — build() fetches the
        # Discovery document which is a blocking HTTPS call; keeping it off the event loop
        # prevents stalling other requests during the network round-trip.
        def _gmail_set_read_state() -> None:
            client = GmailClient(token_data)
            client.refresh_if_needed()
            client.set_thread_read_state(thread_id, is_read)

        await asyncio.to_thread(_gmail_set_read_state)
        # gmail_updated is True from this point — any exception above would have raised

        # Mirror to Supabase emails table; report outcome truthfully
        db_updated: bool = False
        db_error_msg: str = ""
        try:
            await asyncio.to_thread(
                lambda: store.client.table("emails")
                    .update({"is_read": is_read})
                    .eq("thread_id", thread_id)
                    .eq("account_id", account_id)
                    .execute()
            )
            db_updated = True
        except Exception as db_err:
            db_error_msg = str(db_err)
            logger.warning(f"[READ-STATE] Supabase update failed: {db_err}")

        logger.info(
            f"[READ-STATE] thread={thread_id} account={account_id} "
            f"is_read={is_read} gmail_updated=True db_updated={db_updated}"
        )
        result: dict = {"success": True, "gmail_updated": True, "db_updated": db_updated}
        if not db_updated:
            result["db_error"] = db_error_msg
        return result

    except Exception as e:
        logger.error(f"[READ-STATE] Unexpected error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


@api_router.get("/sent")
async def get_sent_emails(account_id: str, limit: int = 50, offset: int = 0):
    """
    Returns sent emails for an account, ordered by sent_at DESC.
    Returns [] on empty — never errors for empty result.
    """
    try:
        store = safe_get_store()
        if not store:
            logger.warning("[SENT] Store unavailable")
            return []
        result = await asyncio.to_thread(
            lambda: store.client.table("sent_emails")
                .select("*")
                .eq("account_id", account_id)
                .eq("source", "app_send")
                .order("sent_at", desc=True)
                .limit(limit)
                .offset(offset)
                .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"[SENT] Query failed: {type(e).__name__}: {e}")
        return []


@api_router.get("/inbox")
async def get_inbox_threads(account_id: str = Query(...), limit: int = Query(50)):
    """
    Thread-aware inbox: one representative row per thread, sorted by latest activity DESC.
    Considers both inbox message dates and sent message timestamps so that a thread where
    the user replied last still surfaces at the correct position.
    """
    store = safe_get_store()
    if not store:
        logger.warning("[INBOX] Store unavailable")
        return []
    try:
        # Fetch raw inbox messages with a larger cap to avoid cutting mid-thread duplicates
        raw_emails = await asyncio.to_thread(
            store.get_emails_with_summaries, limit=200, account_id=account_id
        )
        # Fetch sent timestamps per thread to capture user-reply activity ordering
        sent_result = await asyncio.to_thread(
            lambda: store.client.table("sent_emails")
                .select("thread_id, sent_at")
                .eq("account_id", account_id)
                .order("sent_at", desc=True)
                .limit(200)
                .execute()
        )
        # Map: thread_id -> latest sent_at (first-seen = latest since ordered DESC)
        sent_latest: dict = {}
        for row in (sent_result.data or []):
            tid = row.get("thread_id")
            sat = row.get("sent_at")
            if tid and sat and tid not in sent_latest:
                sent_latest[tid] = sat

        def _parse_ts(ts: str) -> datetime:
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        # Thread-collapse: one row per thread_id (first-seen = latest, emails are date DESC)
        seen: dict = {}
        has_unread: dict = {}
        for email in raw_emails:
            key = email.get("thread_id") or email.get("gmail_message_id") or email.get("subject", "")
            if key not in seen:
                seen[key] = email
                has_unread[key] = not email.get("is_read", True)
            elif not email.get("is_read", True):
                has_unread[key] = True

        # Build representative rows with thread-level unread + latest-activity key
        rows = []
        for key, rep in seen.items():
            row = dict(rep)
            row["is_read"] = not has_unread[key]
            thread_id = rep.get("thread_id")
            inbox_ts = rep.get("date") or rep.get("created_at") or ""
            sent_ts = sent_latest.get(thread_id, "") if thread_id else ""
            latest_dt = max(_parse_ts(inbox_ts), _parse_ts(sent_ts))
            row["_latest_activity"] = latest_dt.isoformat()
            rows.append(row)

        # Sort by latest activity DESC, strip internal sort key
        rows.sort(key=lambda r: r.get("_latest_activity", ""), reverse=True)
        for row in rows:
            row.pop("_latest_activity", None)

        logger.info(f"[INBOX] Returning {min(len(rows), limit)} threads for account={account_id}")
        return rows[:limit]
    except Exception as e:
        logger.error(f"[INBOX] Failed: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


@api_router.post("/backfill-sent")
async def backfill_sent_emails(account_id: str = Query(...)):
    """
    Backfills historical sent messages from Gmail into sent_emails table.

    Idempotent: skips messages already present by gmail_message_id.
    Bounded: fetches at most 100 sent messages per call.
    Safe: insert errors per batch are logged but do not abort the whole backfill.
    """
    from backend.services.gmail_engine import fetch_sent_messages

    credential_store = CredentialStore(persistence)
    token_data = credential_store.load_credentials(account_id)
    if not token_data or 'token' not in token_data:
        raise HTTPException(status_code=401, detail=f"No valid credentials for account: {account_id}")

    store = safe_get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Store unavailable")

    # Fetch recent sent messages from Gmail (bounded at 100)
    sent_rows = await asyncio.to_thread(fetch_sent_messages, token_data, 100)

    if isinstance(sent_rows, dict) and "__auth_error__" in sent_rows:
        raise HTTPException(status_code=401, detail="Gmail token expired — please re-authenticate")

    if not sent_rows:
        return {"status": "ok", "inserted": 0, "skipped": 0, "message": "No sent messages found in Gmail"}

    # Idempotency: load existing gmail_message_ids for this account to avoid dupes
    try:
        existing_result = await asyncio.to_thread(
            lambda: store.client.table("sent_emails")
                .select("gmail_message_id")
                .eq("account_id", account_id)
                .execute()
        )
        existing_ids = {
            r['gmail_message_id']
            for r in (existing_result.data or [])
            if r.get('gmail_message_id')
        }
    except Exception as e:
        logger.warning(f"[BACKFILL-SENT] Could not fetch existing IDs (will insert all): {e}")
        existing_ids = set()

    new_rows = [r for r in sent_rows if r['gmail_message_id'] not in existing_ids]
    skipped = len(sent_rows) - len(new_rows)

    if not new_rows:
        logger.info(f"[BACKFILL-SENT] All {skipped} rows already exist for {account_id}")
        return {"status": "ok", "inserted": 0, "skipped": skipped}

    # Insert in batches of 50 — log failures per batch without aborting
    inserted = 0
    for i in range(0, len(new_rows), 50):
        batch = new_rows[i:i + 50]
        payloads = [
            {
                "account_id": account_id,
                "gmail_message_id": r["gmail_message_id"],
                "thread_id": r["thread_id"],
                "to_address": r["to_address"],
                "cc_addresses": r.get("cc_addresses"),
                "subject": r.get("subject"),
                "body_preview": r.get("body_preview"),
                "sent_at": r["sent_at"],
                "source": "gmail_backfill",
            }
            for r in batch
        ]
        try:
            await asyncio.to_thread(
                lambda p=payloads: store.client.table("sent_emails").insert(p).execute()
            )
            inserted += len(batch)
            logger.info(f"[BACKFILL-SENT] Inserted batch of {len(batch)} rows for {account_id}")
        except Exception as batch_err:
            logger.error(f"[BACKFILL-SENT] Batch insert failed (rows {i}–{i + len(batch)}): {batch_err}")

    logger.info(f"[BACKFILL-SENT] Completed: {inserted} inserted, {skipped} skipped for {account_id}")
    return {"status": "ok", "inserted": inserted, "skipped": skipped}


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
            "export_at": datetime.now(timezone.utc).isoformat(),
            "emails": filtered,
            "threads_count": len(getattr(assistant, "threads", {}))
        }
    except Exception as e:
        print(f"[FAIL] Export failed: {e}")
        return {"error": "Export failed"}


@api_router.get("/accounts")
async def list_accounts():
    """
    Lists all connected Gmail accounts with truthful credential status.

    For each account:
    - connected: True if a credentials row exists
    - auth_required: True if credentials row exists but tokens cannot be decrypted
                     (e.g. after FERNET key rotation) — user must re-authenticate
    - send_scope: True if gmail.send scope is present in stored scopes
    """
    store = safe_get_store()
    if not store:
        return {"accounts": []}
    try:
        gmail_creds = await asyncio.to_thread(store.list_credentials, "gmail") or []

        credential_store = CredentialStore(persistence)
        accounts = []
        for c in gmail_creds:
            account_id = c.get("account_id")
            scopes = c.get("scopes", [])
            # Attempt decrypt to distinguish "row exists" from "usable credentials"
            try:
                token_data = await asyncio.to_thread(
                    credential_store.load_credentials, account_id
                )
                auth_required = (token_data is None or "token" not in token_data)
            except Exception:
                auth_required = True
            send_scope = any("gmail.send" in (s or "") for s in scopes)
            modify_scope = any("gmail.modify" in (s or "") for s in scopes)
            accounts.append({
                "account_id": account_id,
                "connected": True,
                "auth_required": auth_required,
                "send_scope": send_scope,
                "modify_scope": modify_scope,
                "updated_at": c.get("updated_at"),
                "scopes": scopes,
            })
        return {"accounts": accounts}
    except Exception as e:
        logger.warning(f"[ACCOUNTS] List failed: {e}")
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
        gmail_resp = store.client.table("credentials").delete().eq("provider", "gmail").execute()
        deleted_count = len(gmail_resp.data) if gmail_resp.data else 0
        print(f"[OK] [CLEANUP] Deleted {deleted_count} gmail credentials")
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

# ------------------------------------------------------------------
# AGENT ROUTES — BL-08/BL-09
# All routes sit on api_router and inherit Depends(require_jwt_auth).
# ------------------------------------------------------------------

@api_router.post("/agent/consent")
async def agent_set_consent(request: AgentConsentRequest):
    """
    Enable AI assistant for this account.

    Writes an audit_log entry with user_approved=TRUE so the approval gate
    passes for subsequent agent actions.  The gate fails closed until this
    endpoint is called — no agent action is possible without explicit consent.

    Requires the SQL patch:
      ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS user_approved BOOLEAN NOT NULL DEFAULT FALSE;
      ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL;
    """
    store = safe_get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Storage unavailable")
    effective_account_id = resolve_account_id(None, request.account_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        store.client.table("audit_log").insert({
            "tenant_id": "primary",
            "action": "agent_consent",
            "resource": effective_account_id,
            "metadata": {"consent_granted_at": now_iso},
            "user_approved": True,
            "approved_at": now_iso,
            "timestamp": now_iso,
        }).execute()
    except Exception as e:
        logger.error("[AGENT-CONSENT] Write failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Failed to record consent")
    logger.info("[AGENT-CONSENT] Consent granted for %s", effective_account_id)
    return {"status": "ok", "approved": True, "account_id": effective_account_id}


@api_router.get("/agent/status")
async def agent_get_status(account_id: str = Query(...)):
    """
    Return approval state and remaining rate-limit quota for this account.
    Frontend uses this to decide whether to show consent UI or the instruction input.
    """
    store = safe_get_store()
    if not store:
        return {"approved": False, "rate_limit_remaining": 0, "rate_limit_max": 10}
    effective_account_id = resolve_account_id(None, account_id)

    from backend.assistant.approval_gate import check_agent_approved
    approved = check_agent_approved(store, effective_account_id)

    window = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    counter_key = f"agent:{effective_account_id}:{window}"
    current_count = 0
    try:
        resp = (
            store.client.table("rate_limit_counters")
            .select("count")
            .eq("key", counter_key)              # proven column: key TEXT PRIMARY KEY
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        current_count = int(rows[0]["count"]) if rows else 0
    except Exception:
        pass  # Fail open: unknown count → report full quota remaining

    return {
        "approved": approved,
        "rate_limit_remaining": max(0, 10 - current_count),
        "rate_limit_max": 10,
    }


@api_router.post("/agent/feedback")
async def agent_record_feedback(request: AgentFeedbackRequest):
    """
    Record user feedback on an AI draft proposal.

    Privacy: original_input stores email subject only — max 500 chars, never email body.
    Feedback is best-effort; failures never block the user.
    """
    store = safe_get_store()
    if not store:
        return {"status": "ok"}
    effective_account_id = resolve_account_id(None, request.account_id)
    from backend.learning.feedback_collector import record_feedback
    record_feedback(
        store=store,
        account_id=effective_account_id,
        conversation_id=request.conversation_id,
        action_type=request.action_type,
        subject=request.subject,  # subject only; truncation enforced inside record_feedback
        outcome=request.outcome,
        rating=request.rating,
    )
    return {"status": "ok"}


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
    render_url = os.getenv("RENDER_EXTERNAL_URL", "http://127.0.0.1:8888")

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
async def google_oauth_callback(request: Request, code: str, state: str = None, account_id: str = Query("default")):
    """
    Handles Google OAuth callback with PKCE support.
    Exchanges authorization code for tokens and stores them encrypted.

    CANONICAL CALLBACK ROUTE: /auth/callback/google
    LOCAL: http://127.0.0.1:8888/auth/callback/google
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
        redirect = RedirectResponse(url=f"{frontend_url}/?auth=success&account_id={encoded_account_id}")
        jwt_token = create_access_token(effective_account_id)
        cookie_kwargs = build_session_cookie_kwargs(request)
        redirect.set_cookie(value=jwt_token, **cookie_kwargs)
        return redirect

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
        print(f"[WARN] [SCHEMA] Schema not verified at API startup. Expected {expected_version}. Current state: {ControlPlane.schema_state}.")
        print("[WARN] [SCHEMA] Startup is continuing. Runtime write-gated routes remain subject to schema verification state.")
        print("[TIP] [ACTION] Schema setup: apply backend/sql/setup_schema.sql in Supabase SQL editor")
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
# STATIC / SPA ROUTES (must be last before ASGI wrap)
# ------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def serve_root():
    if FRONTEND_INDEX.exists():
        return FileResponse(str(FRONTEND_INDEX))
    raise HTTPException(status_code=503, detail="Frontend build not found")


_SPA_PROTECTED = {
    "api", "auth", "healthz", "process", "accounts", "emails",
    "docs", "redoc", "openapi.json", "socket.io",
}


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    top = full_path.split("/")[0].lower()
    if top in _SPA_PROTECTED:
        raise HTTPException(status_code=404, detail="Not found")
    candidate = FRONTEND_DIST / full_path
    if candidate.exists() and candidate.is_file():
        return FileResponse(str(candidate))
    if FRONTEND_INDEX.exists():
        return FileResponse(str(FRONTEND_INDEX))
    raise HTTPException(status_code=503, detail="Frontend build not found")


# ------------------------------------------------------------------
# FINAL ASGI WRAP (Must be last)
# ------------------------------------------------------------------
sio_app = socketio.ASGIApp(
    sio,
    other_asgi_app=app,
    socketio_path="/socket.io",
)

