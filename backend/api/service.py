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
import inspect
import mimetypes
import os
import sys
import logging
from pathlib import Path

import asyncio
import json
import re

try:
    from bs4 import BeautifulSoup as _BeautifulSoup, NavigableString as _NavigableString
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False
import time
from datetime import datetime, timezone
from html import escape
from typing import Dict, Any, List, Optional, Tuple
from email.utils import parseaddr

from fastapi import FastAPI, HTTPException, Request, Response, APIRouter, Query, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
import socketio

from backend.infrastructure.supabase_store import SupabaseStore
from backend.infrastructure.mistral_governor import get_governor as _get_mistral_governor
from backend.languages import (
    normalize_language,
    normalize_translation_language,
    get_translation_label,
    SUPPORTED_LANGUAGES,
    TRANSLATION_LANGUAGES,
    DEFAULT_LANGUAGE,
)
from backend.tones import SUPPORTED_TONES, normalize_tone, list_supported_tones
from backend.summary_versions import EMAIL_SUMMARY_PROMPT_VERSION
from backend.engine.nlp_engine import MistralEngine
from backend.utils.summary_utils import resolve_summary_for_language

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
    logger=False,
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
    api_timestamp = datetime.now(timezone.utc).isoformat()

    commit_sha_candidate = (os.getenv("COMMIT_SHA") or "").strip()
    render_commit_sha_candidate = (os.getenv("RENDER_GIT_COMMIT") or "").strip()

    if re.fullmatch(r"[0-9a-fA-F]{7,40}", commit_sha_candidate):
        commit_sha = commit_sha_candidate
    elif re.fullmatch(r"[0-9a-fA-F]{7,40}", render_commit_sha_candidate):
        commit_sha = render_commit_sha_candidate
    else:
        commit_sha = "unknown"

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
        "api_timestamp": api_timestamp,
        "commit_sha": commit_sha,
        "deployed_at": os.getenv("DEPLOYED_AT") or api_timestamp,
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

    inbox_response = (
        store.client.table("emails")
        .select("account_id,body,subject,sender,date,gmail_message_id,thread_id")
        .eq("gmail_message_id", gmail_message_id)
        .limit(1)
        .execute()
    )
    if inbox_response.data:
        return inbox_response.data[0]

    sent_response = (
        store.client.table("sent_emails")
        .select("account_id,gmail_message_id,thread_id,subject,body_preview,sent_at,to_address,source")
        .eq("gmail_message_id", gmail_message_id)
        .limit(1)
        .execute()
    )
    if not sent_response.data:
        return None

    sent_row = sent_response.data[0]
    return {
        "account_id": sent_row.get("account_id"),
        "body": sent_row.get("body_preview") or "",
        "subject": sent_row.get("subject"),
        "sender": None,
        "date": sent_row.get("sent_at"),
        "gmail_message_id": sent_row.get("gmail_message_id"),
        "thread_id": sent_row.get("thread_id"),
        "source": sent_row.get("source"),
    }


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
async def list_emails_with_summaries(account_id: Optional[str] = Query(None), preferred_language: str = Query("en")):
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
        preferred_language = normalize_language(preferred_language)
        logger.info(f"[API] /emails-with-summaries called with account_id={account_id}")
        emails = await asyncio.to_thread(
            store.get_emails_with_summaries, account_id=account_id, preferred_language=preferred_language
        )
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
    account_id: str = Query("default"),
    preferred_language: str = Query("en"),
):
    """
    Fetch AI summary for specific email.

    Prefers the preferred_language variant; falls back to English if absent.

    Returns:
        - summary_json: {overview, action_items, urgency} if ready
        - status: "ready"|"processing"|"failed"|"not_found"
        - ai_summary_language: actual language of the returned row
        - ai_summary_is_fallback: True when preferred variant was absent
        - ai_preferred_language: the requested language
        - ai_preferred_language_available: whether the preferred variant exists
    """
    effective_account_id = resolve_account_id(None, account_id)
    preferred_language = normalize_language(preferred_language)
    store = safe_get_store()
    if not store:
        return {"status": "error", "message": "Store unavailable"}

    try:
        # Fetch all email-summary language variants for this message.
        # Filtering by prompt_version excludes document-summary rows from this shared table.
        response = await asyncio.to_thread(
            lambda: store.client.table("email_ai_summaries")
                .select("*")
                .eq("account_id", effective_account_id)
                .eq("gmail_message_id", gmail_message_id)
                .eq("prompt_version", EMAIL_SUMMARY_PROMPT_VERSION)
                .execute()
        )

        rows = response.data or []
        if rows:
            # Build per-language index (newest per language wins if duplicates exist)
            rows_sorted = sorted(rows, key=lambda r: r.get("updated_at") or "", reverse=True)
            summary = (
                resolve_summary_for_language(rows_sorted, preferred_language)
                or rows_sorted[0]
            )
            preferred_available = any(
                r.get("summary_language", "en") == preferred_language
                for r in rows_sorted
            )
            actual_lang = summary.get("summary_language", "en")

            return {
                "status": "ready",
                "summary_json": summary.get("summary_json"),
                "summary_text": summary.get("summary_text"),
                "model": summary.get("model"),
                "created_at": summary.get("created_at"),
                "ai_summary_language": actual_lang,
                "ai_summary_is_fallback": actual_lang != preferred_language,
                "ai_preferred_language": preferred_language,
                "ai_preferred_language_available": preferred_available,
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
    tone: Optional[str] = "professional"


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
    normalized_tone = normalize_tone(request.tone)

    try:
        result = await agent.propose_draft(
            account_id=effective_account_id,
            thread_id=thread_id,                 # proven column: thread_id TEXT NOT NULL
            subject=subject,
            sender=sender,
            body_excerpt=body_excerpt,
            user_instruction=request.user_instruction,
            conversation_id=request.conversation_id,
            tone=normalized_tone,
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


_MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # 25 MB total across all attachments

_BLOCKED_EXTENSIONS: frozenset = frozenset({
    ".ade", ".adp", ".apk", ".appx", ".appxbundle", ".bat", ".cab", ".chm",
    ".cmd", ".com", ".cpl", ".diagcab", ".diagcfg", ".diagpkg", ".dll", ".dmg",
    ".ex", ".ex_", ".exe", ".hta", ".img", ".ins", ".iso", ".isp", ".jar",
    ".jnlp", ".js", ".jse", ".lib", ".lnk", ".mde", ".mjs", ".msc", ".msi",
    ".msix", ".msixbundle", ".msp", ".mst", ".nsh", ".pif", ".ps1", ".scr",
    ".sct", ".shb", ".sys", ".vb", ".vbe", ".vbs", ".vhd", ".vxd", ".wsc",
    ".wsf", ".wsh", ".xll",
})


class SendEmailRequest(BaseModel):
    """Request model for sending email replies - backend owns reply context."""
    body: str
    subject: Optional[str] = None
    cc: Optional[str] = None


@api_router.post("/threads/{thread_id}/send")
async def send_thread_reply(thread_id: str, request: Request):
    """
    Send an email reply with RFC-compliant threading headers.
    Backend owns reply context derivation - client only provides draft text.

    Accepts both:
      - application/json: {"body": "...", "subject": "...", "cc": "..."}
      - multipart/form-data: body + optional subject/cc + repeated 'attachments' parts

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

        # Parse request body — JSON or multipart/form-data
        content_type = request.headers.get("content-type", "")
        validated_attachments: List[Dict[str, Any]] = []

        if "multipart/form-data" in content_type:
            form = await request.form()
            body_text: str = str(form.get("body", "") or "")
            subject_val: Optional[str] = str(form.get("subject")) if form.get("subject") else None
            cc_val: Optional[str] = str(form.get("cc")) if form.get("cc") else None

            raw_files = form.getlist("attachments")
            total_bytes = 0
            for upload in raw_files:
                if (
                    isinstance(upload, str)
                    or not hasattr(upload, "filename")
                    or not hasattr(upload, "read")
                    or not callable(upload.read)
                ):
                    logger.warning(f"[SEND] Skipping non-file multipart part: {type(upload)}")
                    continue
                try:
                    filename = getattr(upload, "filename", None) or "attachment"
                    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                    if ext in _BLOCKED_EXTENSIONS:
                        return {
                            "success": False,
                            "error": f"Attachment '{filename}' has a blocked file type ({ext}). Remove it and retry.",
                        }
                    _read_result = upload.read()
                    content_bytes = await _read_result if inspect.isawaitable(_read_result) else _read_result
                    total_bytes += len(content_bytes)
                    if total_bytes > _MAX_ATTACHMENT_BYTES:
                        return {
                            "success": False,
                            "error": (
                                f"Total attachment size exceeds the 25 MB limit "
                                f"({total_bytes / (1024 * 1024):.1f} MB). Reduce attachments and retry."
                            ),
                        }
                    raw_ct = getattr(upload, "content_type", None)
                    att_content_type = raw_ct or mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    validated_attachments.append({
                        "filename": filename,
                        "content_type": att_content_type,
                        "content_bytes": content_bytes,
                    })
                finally:
                    if hasattr(upload, "close") and callable(upload.close):
                        _close_result = upload.close()
                        if inspect.isawaitable(_close_result):
                            await _close_result
            logger.info(f"[SEND] Multipart request — {len(validated_attachments)} attachment(s), {total_bytes} bytes")
        else:
            json_data = await request.json()
            body_text = json_data.get("body", "") or ""
            subject_val = json_data.get("subject") or None
            cc_val = json_data.get("cc") or None

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
        client_subject = (subject_val or '').strip()
        base_subject = client_subject if client_subject else raw_subject
        subject = base_subject if base_subject.lower().startswith('re:') else f"Re: {base_subject}"

        logger.info(f"[SEND] Reply context - Subject: {subject}, To: {recipient}")

        # Step 8: Normalize and validate CC addresses
        normalized_cc = ''
        if cc_val:
            seen: set = set()
            valid_addrs: list = []
            for raw in re.split(r'[,;]', cc_val):
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
            body=body_text,
            gmail_thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
            cc=normalized_cc or None,
            attachments=validated_attachments or None,
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
                        "body_preview": body_text[:200],
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                        "source": "app_send",
                        "has_attachments": len(validated_attachments) > 0,
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
async def get_inbox_threads(account_id: str = Query(...), limit: int = Query(50), preferred_language: str = Query("en")):
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
        preferred_language = normalize_language(preferred_language)
        # Fetch raw inbox messages with a larger cap to avoid cutting mid-thread duplicates
        raw_emails = await asyncio.to_thread(
            store.get_emails_with_summaries, limit=200, account_id=account_id,
            preferred_language=preferred_language
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
        thread_counts: dict = {}
        for email in raw_emails:
            key = email.get("thread_id") or email.get("gmail_message_id") or email.get("subject", "")
            thread_counts[key] = thread_counts.get(key, 0) + 1
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
            row["thread_count"] = thread_counts.get(key, 1)
            thread_id = rep.get("thread_id")
            inbox_ts = rep.get("date") or rep.get("created_at") or ""
            sent_ts = sent_latest.get(thread_id, "") if thread_id else ""
            latest_dt = max(_parse_ts(inbox_ts), _parse_ts(sent_ts))
            row["last_activity_iso"] = latest_dt.isoformat()
            row["last_sender"] = row.get("sender", "")
            rows.append(row)

        # Sort by latest activity DESC
        rows.sort(key=lambda r: r.get("last_activity_iso", ""), reverse=True)

        logger.info(f"[INBOX] Returning {min(len(rows), limit)} threads for account={account_id}")
        return rows[:limit]
    except Exception as e:
        logger.error(f"[INBOX] Failed: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


@api_router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    account_id: str = Query(...),
    preferred_language: str = Query("en"),
):
    """
    Returns inbox-side messages for a single thread,
    sorted chronologically ascending (oldest first).
    """
    store = safe_get_store()
    if not store:
        logger.warning("[THREAD_MESSAGES] Store unavailable")
        return []
    try:
        preferred_language = normalize_language(preferred_language)
        raw_emails = await asyncio.to_thread(
            store.get_emails_with_summaries, limit=200, account_id=account_id,
            preferred_language=preferred_language
        )
        messages = [e for e in raw_emails if e.get("thread_id") == thread_id]
        messages.sort(key=lambda e: e.get("date") or e.get("created_at") or "")
        logger.info(
            f"[THREAD_MESSAGES] Returning {len(messages)} messages"
            f" for thread={thread_id} account={account_id}"
        )
        return messages
    except Exception as e:
        logger.error(f"[THREAD_MESSAGES] Failed: {type(e).__name__}: {e}")
        return []


@api_router.get("/search")
async def search_emails(
    q: str = Query(...),
    account_id: str = Query(...),
    preferred_language: str = Query("en"),
    limit: int = Query(50),
    has_attachments: Optional[bool] = Query(None),
):
    """
    Full-text search over the inbox.  Returns InboxThreadRow-compatible dicts.

    Uses the DB function search_emails_ranked_v3 (ts_rank over search_vector) for
    server-side ranked candidates, then applies the same summary-enrichment,
    sent-activity merge, thread-collapse, and unread-propagation logic as
    /api/inbox.  Results are sorted by relevance DESC, latest activity DESC.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return []
    limit = min(max(limit, 1), 50)
    preferred_language = normalize_language(preferred_language)

    store = safe_get_store()
    if not store:
        logger.warning("[SEARCH] Store unavailable")
        return []

    try:
        # 1. Fetch ranked candidates from the DB function (bounded at 200)
        rpc_result = await asyncio.to_thread(
            lambda: store.client.rpc(
                "search_emails_ranked_v3",
                {"p_account_id": account_id, "p_query": q, "p_limit": 200, "p_has_attachments": has_attachments},
            ).execute()
        )
        candidates = rpc_result.data or []
        if not candidates:
            logger.info(f"[SEARCH] No candidates for q={q!r} account={account_id}")
            return []

        # 2. Build gmail_message_id -> candidate map; preserve rank
        cand_map: dict = {}
        for row in candidates:
            mid = row.get("gmail_message_id")
            if mid and mid not in cand_map:
                cand_map[mid] = row

        # 3. Fetch summaries for candidate message IDs
        message_ids = list(cand_map.keys())
        summaries_map: dict = {}
        try:
            if not message_ids:
                raise ValueError("empty message_ids — skip summary query")
            summ_result = await asyncio.to_thread(
                lambda: store.client.table("email_ai_summaries")
                    .select("*")
                    .eq("account_id", account_id)
                    .in_("gmail_message_id", message_ids)
                    .eq("prompt_version", EMAIL_SUMMARY_PROMPT_VERSION)
                    .execute()
            )
            sorted_summ = sorted(
                summ_result.data or [],
                key=lambda s: s.get("updated_at") or "",
                reverse=True,
            )
            grouped: dict = {}
            for s in sorted_summ:
                mid = s.get("gmail_message_id")
                if not mid:
                    continue
                grouped.setdefault(mid, []).append(s)
            for mid, mid_rows in grouped.items():
                chosen = (
                    resolve_summary_for_language(mid_rows, preferred_language)
                    or mid_rows[0]
                )
                preferred_available = any(
                    r.get("summary_language", "en") == preferred_language
                    for r in mid_rows
                )
                summaries_map[mid] = {
                    "row": chosen,
                    "preferred_available": preferred_available,
                }
        except Exception as summ_err:
            logger.warning(f"[SEARCH] Summary fetch failed (non-fatal): {type(summ_err).__name__}: {summ_err}")

        # 4. Merge summary fields into each candidate
        def _merge_summary(email: dict) -> dict:
            mid = email.get("gmail_message_id")
            entry = summaries_map.get(mid) if mid else None
            if entry:
                summary = entry["row"]
                actual_lang = summary.get("summary_language", "en")
                email["ai_summary_json"] = summary.get("summary_json")
                email["ai_summary_text"] = summary.get("summary_text")
                email["ai_summary_model"] = summary.get("model")
                email["ai_summary_language"] = actual_lang
                email["ai_summary_is_fallback"] = actual_lang != preferred_language
                email["ai_preferred_language"] = preferred_language
                email["ai_preferred_language_available"] = entry["preferred_available"]
            else:
                email["ai_summary_json"] = None
                email["ai_summary_text"] = None
                email["ai_summary_model"] = None
                email["ai_summary_language"] = None
                email["ai_summary_is_fallback"] = False
                email["ai_preferred_language"] = preferred_language
                email["ai_preferred_language_available"] = False
            return email

        enriched = [_merge_summary(dict(row)) for row in candidates]

        # 5. Fetch sent_emails timestamps for latest-activity parity
        sent_result = await asyncio.to_thread(
            lambda: store.client.table("sent_emails")
                .select("thread_id, sent_at")
                .eq("account_id", account_id)
                .order("sent_at", desc=True)
                .limit(200)
                .execute()
        )
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

        # 6. Thread collapse: one representative per thread (highest rank wins;
        #    tie-break by latest activity DESC); propagate thread-level unread.
        #    Four separate dicts prevent any bleed between representative state
        #    and thread-wide aggregate state.
        seen: dict = {}                  # key -> representative row
        best_rank: dict = {}             # key -> float rank of the representative
        rep_latest_activity: dict = {}   # key -> datetime of the representative row
        thread_latest_activity: dict = {}# key -> datetime of the most-active row in thread
        has_unread: dict = {}            # key -> bool (any message unread)

        _epoch = datetime.min.replace(tzinfo=timezone.utc)

        for email in enriched:
            key = email.get("thread_id") or email.get("gmail_message_id") or email.get("subject", "")
            rank = float(email.get("rank") or 0.0)
            thread_id = email.get("thread_id")
            inbox_ts = email.get("date") or email.get("created_at") or ""
            sent_ts = sent_latest.get(thread_id, "") if thread_id else ""
            latest_dt = max(_parse_ts(inbox_ts), _parse_ts(sent_ts))

            # Always track thread-wide latest activity
            thread_latest_activity[key] = max(
                thread_latest_activity.get(key, _epoch), latest_dt
            )

            if key not in seen:
                seen[key] = email
                best_rank[key] = rank
                rep_latest_activity[key] = latest_dt
                has_unread[key] = not email.get("is_read", True)
            else:
                # Replace representative only when this row is strictly better:
                # higher rank wins; equal rank resolved by more recent row activity.
                if rank > best_rank[key] or (
                    rank == best_rank[key] and latest_dt > rep_latest_activity[key]
                ):
                    seen[key] = email
                    best_rank[key] = rank
                    rep_latest_activity[key] = latest_dt

            if not email.get("is_read", True):
                has_unread[key] = True

        # 7. Build final rows with thread-level unread and sort keys
        rows = []
        for key, rep in seen.items():
            row = dict(rep)
            row["is_read"] = not has_unread[key]
            row["_rank"] = best_rank[key]
            row["last_activity_iso"] = thread_latest_activity[key].isoformat()
            # last_sender from highest-rank representative.
            # Recency not guaranteed. Inbox route preferred
            # for polarity derivation.
            row["last_sender"] = row.get("sender", "")
            rows.append(row)

        rows.sort(
            key=lambda r: (r.get("_rank", 0.0), r.get("last_activity_iso", "")),
            reverse=True,
        )
        for row in rows:
            row.pop("_rank", None)
            row.pop("rank", None)

        logger.info(f"[SEARCH] Returning {min(len(rows), limit)} threads for q={q!r} account={account_id}")
        return rows[:limit]

    except Exception as e:
        logger.error(f"[SEARCH] Failed: {type(e).__name__}: {e}")
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
    existing_rows = [r for r in sent_rows if r['gmail_message_id'] in existing_ids]
    skipped = len(existing_rows)

    # Insert new rows in batches of 50 — log failures per batch without aborting
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
                "has_attachments": bool(r.get("has_attachments", False)),
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

    # Refresh has_attachments on rows that already exist in the DB — no other columns touched
    refreshed = 0
    for r in existing_rows:
        mid = r["gmail_message_id"]
        v = bool(r.get("has_attachments", False))
        try:
            await asyncio.to_thread(
                lambda: store.client.table("sent_emails")
                    .update({"has_attachments": v})
                    .eq("account_id", account_id)
                    .eq("gmail_message_id", mid)
                    .execute()
            )
            refreshed += 1
        except Exception as ref_err:
            logger.error(f"[BACKFILL-SENT] Refresh failed for {mid}: {ref_err}")

    logger.info(
        f"[BACKFILL-SENT] Completed: {inserted} inserted, {skipped} existing "
        f"({refreshed} refreshed) for {account_id}"
    )
    return {"status": "ok", "inserted": inserted, "skipped": skipped, "refreshed": refreshed}


@api_router.post("/maintenance/correct-inbox-attachments")
async def correct_inbox_attachments(
    account_id: str = Query(...),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """
    Correction of has_attachments for historical inbox emails — one bounded,
    ordered batch per call.

    Candidates are selected in a stable deterministic order (created_at ASC,
    id ASC) so repeated calls with advancing offset sweep the full dataset
    without gaps or re-processing.

    Query params:
        account_id  — required; scopes correction to one account
        limit       — batch size (1–200, default 50)
        offset      — skip this many rows before the batch (default 0)

    Returns: {scanned, updated_true, updated_false, skipped, errors, limit, offset}
    """
    from backend.providers.gmail import GmailProvider
    from backend.api.gmail_client import GmailClient as WorkerGmailClient
    from backend.services.gmail_engine import gmail_payload_has_attachments

    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)

    store = safe_get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Store unavailable")

    provider = GmailProvider()
    token_data = provider._load_token_data(account_id)
    if not token_data or "token" not in token_data:
        raise HTTPException(status_code=401, detail=f"No valid credentials for account: {account_id}")

    gmail_client = WorkerGmailClient(provider._build_worker_token_data(token_data))

    try:
        db_result = await asyncio.to_thread(
            lambda: store.client.table("emails")
                .select("id,gmail_message_id")
                .eq("account_id", account_id)
                .order("created_at", desc=False)
                .order("id", desc=False)
                .offset(offset)
                .limit(limit)
                .execute()
        )
        rows = db_result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB fetch failed: {e}")

    scanned = len(rows)
    updated_true = 0
    updated_false = 0
    skipped = 0
    errors = 0

    for row in rows:
        msg_id = row.get("gmail_message_id")
        if not msg_id:
            skipped += 1
            continue
        row_id = row["id"]
        try:
            raw_msg = await asyncio.to_thread(gmail_client.get_message, msg_id)
            if not raw_msg:
                skipped += 1
                continue
            payload = raw_msg.get("payload", {}) or {}
            has_att = gmail_payload_has_attachments(payload)
            await asyncio.to_thread(
                lambda: store.client.table("emails")
                    .update({"has_attachments": has_att})
                    .eq("id", row_id)
                    .execute()
            )
            if has_att:
                updated_true += 1
            else:
                updated_false += 1
        except Exception as e:
            logger.error(
                f"[INBOX-CORRECTION] {account_id} msg={msg_id[:8]}...: "
                f"{type(e).__name__}: {e}"
            )
            errors += 1

    logger.info(
        f"[INBOX-CORRECTION] account={account_id} scanned={scanned} "
        f"true={updated_true} false={updated_false} skipped={skipped} errors={errors} "
        f"offset={offset} limit={limit}"
    )
    return {
        "status": "ok",
        "scanned": scanned,
        "updated_true": updated_true,
        "updated_false": updated_false,
        "skipped": skipped,
        "errors": errors,
        "limit": limit,
        "offset": offset,
    }


@api_router.post("/maintenance/correct-sent-attachments")
async def correct_sent_attachments(
    account_id: str = Query(...),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """
    Correction of has_attachments for historical sent emails — one bounded,
    ordered batch per call.

    Candidates are selected in a stable deterministic order (sent_at ASC,
    id ASC) so repeated calls with advancing offset sweep the full dataset
    without gaps or re-processing.

    Query params:
        account_id  — required; scopes correction to one account
        limit       — batch size (1–200, default 50)
        offset      — skip this many rows before the batch (default 0)

    Returns: {scanned, updated_true, updated_false, skipped, errors, limit, offset}
    """
    from backend.providers.gmail import GmailProvider
    from backend.api.gmail_client import GmailClient as WorkerGmailClient
    from backend.services.gmail_engine import gmail_payload_has_attachments

    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)

    store = safe_get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Store unavailable")

    provider = GmailProvider()
    token_data = provider._load_token_data(account_id)
    if not token_data or "token" not in token_data:
        raise HTTPException(status_code=401, detail=f"No valid credentials for account: {account_id}")

    gmail_client = WorkerGmailClient(provider._build_worker_token_data(token_data))

    try:
        db_result = await asyncio.to_thread(
            lambda: store.client.table("sent_emails")
                .select("id,gmail_message_id")
                .eq("account_id", account_id)
                .order("sent_at", desc=False)
                .order("id", desc=False)
                .offset(offset)
                .limit(limit)
                .execute()
        )
        rows = db_result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB fetch failed: {e}")

    scanned = len(rows)
    updated_true = 0
    updated_false = 0
    skipped = 0
    errors = 0

    for row in rows:
        msg_id = row.get("gmail_message_id")
        if not msg_id:
            skipped += 1
            continue
        row_id = row["id"]
        try:
            raw_msg = await asyncio.to_thread(gmail_client.get_message, msg_id)
            if not raw_msg:
                skipped += 1
                continue
            payload = raw_msg.get("payload", {}) or {}
            has_att = gmail_payload_has_attachments(payload)
            await asyncio.to_thread(
                lambda: store.client.table("sent_emails")
                    .update({"has_attachments": has_att})
                    .eq("id", row_id)
                    .execute()
            )
            if has_att:
                updated_true += 1
            else:
                updated_false += 1
        except Exception as e:
            logger.error(
                f"[SENT-CORRECTION] {account_id} msg={msg_id[:8]}...: "
                f"{type(e).__name__}: {e}"
            )
            errors += 1

    logger.info(
        f"[SENT-CORRECTION] account={account_id} scanned={scanned} "
        f"true={updated_true} false={updated_false} skipped={skipped} errors={errors} "
        f"offset={offset} limit={limit}"
    )
    return {
        "status": "ok",
        "scanned": scanned,
        "updated_true": updated_true,
        "updated_false": updated_false,
        "skipped": skipped,
        "errors": errors,
        "limit": limit,
        "offset": offset,
    }


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

class PreferencesUpdateRequest(BaseModel):
    account_id: str
    ai_language: str


class PreferencesProfileUpdateRequest(BaseModel):
    account_id: str
    ai_priority_profile: Optional[Dict[str, Any]] = None


class TemplateCreateRequest(BaseModel):
    account_id: str
    name: str
    tone: Optional[str] = "professional"
    language: str
    body: str


class TranslateEmailRequest(BaseModel):
    body: str
    target_language: str


class TranslateRenderRequest(BaseModel):
    target_language: str


def _get_preferences_store() -> SupabaseStore:
    """Create a Supabase store for preference reads/writes."""
    return SupabaseStore()


def _build_translation_system_prompt(
    target_language: str,
    protected_tokens: Optional[List[str]] = None,
) -> str:
    target_label = get_translation_label(target_language)
    protected_rule = ""
    if protected_tokens:
        token_list = " ".join(protected_tokens)
        protected_rule = (
            f"\n- Preserve ALL placeholder tokens of the form [[PROT_N]] EXACTLY as-is "
            f"without any modification, translation, or removal. "
            f"Current tokens: {token_list}"
        )
    return (
        "You are a professional email translator.\n\n"
        f"Translate the provided email body into {target_label}.\n\n"
        "Rules:\n"
        "- Return only the translated email body text.\n"
        "- Do not add commentary, notes, explanations, titles, or quotation marks.\n"
        "- Preserve paragraph breaks, bullet points, numbering, and blank lines.\n"
        "- Preserve names, email addresses, URLs, phone numbers, dates, times, codes, "
        "and reference numbers exactly unless ordinary surrounding prose requires inflection.\n"
        "- Preserve the professional tone and intent faithfully.\n"
        f"- Translate body content only.{protected_rule}"
    )


# ---------------------------------------------------------------------------
# Structured HTML translation helpers — used by the translate-render endpoint
# ---------------------------------------------------------------------------

# HTML tags whose subtree must not be extracted or translated
_HTML_SKIP_TAGS = frozenset({
    "script", "style", "meta", "link", "form", "head",
    "noscript", "svg", "math", "title",
})

# Inline style patterns that mark an element as hidden/non-user-visible.
# Narrow, evidence-backed list — covers the dominant email preheader hiding techniques.
_HIDDEN_STYLE_PATTERNS = re.compile(
    r"display\s*:\s*none"
    r"|visibility\s*:\s*hidden"
    r"|opacity\s*:\s*0(?!\.[1-9])"   # 0 / 0.0 / 0px — but not 0.1..0.9
    r"|mso-hide\s*:\s*all"
    r"|max-height\s*:\s*0px"         # CSS collapse trick
    r"|font-size\s*:\s*0px",         # zero-font-size preheader trick
    re.IGNORECASE,
)

# Class/ID name fragments that signal a preheader/preview container.
_HIDDEN_CLASS_ID_PATTERN = re.compile(r"\bpreheader\b", re.IGNORECASE)

# For collapsing excessive blank lines in derived plain text.
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")

# Placeholder token pattern used in the protected-token derivation path.
# Tokens of the form [[PROT_N]] stand for protected visible content that must
# not be translated.  The double-bracket prefix is rare in email prose and
# makes the instruction to the model unambiguous.
_PROTECTED_PLACEHOLDER_RE = re.compile(r"\[\[PROT_\d+\]\]")

# Class/ID fragments that identify footer/social/unsubscribe noise in rich HTML.
# Used only in the preflight-degraded path to derive a cleaner fallback source.
_SIMPLIFIED_NOISE_CLASS_ID_RE = re.compile(
    r"\b(footer|social|unsubscribe|unsub|opt[-_]?out|"
    r"view[-_]?(?:in[-_]?)?(?:browser|online)|"
    r"mailing[-_]?address|copyright[-_]?notice|"
    r"manage[-_]?(?:prefs?|preferences|subscriptions?))\b",
    re.IGNORECASE,
)

# Preference guard thresholds for the simplified fallback source selection.
# The derived source must be at least this many characters (substance check)
# and must shrink the existing body by at least (1 - ratio) to be preferred.
_SIMPLIFIED_SOURCE_MIN_CHARS = 50
_SIMPLIFIED_SOURCE_MAX_RATIO = 0.9

# Noise-signal regex for plain-text source quality scoring (preflight-degraded path).
# Targets footer/social/unsubscribe keywords to detect noisier sources.
_FOOTER_NOISE_SIGNAL_RE = re.compile(
    r"\b(?:unsubscribe|opt[\s\-_]?out|"
    r"manage\s+(?:prefs?|subscriptions?|preferences)|"
    r"view\s+(?:in\s+)?(?:browser|online)|"
    r"mailing\s+address|"
    r"copyright\s+\d{4}|"
    r"all\s+rights\s+reserved|"
    r"privacy\s+policy|"
    r"terms\s+of\s+(?:service|use)|"
    r"follow\s+us|connect\s+with\s+us|"
    r"©\s*\d{4})\b",
    re.IGNORECASE,
)
_LINK_CLOUD_LINE_RE = re.compile(r"^\s*(?:\S*https?://\S*\s*){2,}\s*$")
_SEPARATOR_LINE_RE = re.compile(r"^\s*[-=*_·•]{3,}\s*$")
# Noise-gap above which body_text is considered clearly canonical over derived source.
_NOISE_GAP_CANONICAL_PREFERENCE = 3.0

# Block-level HTML tags that receive blank-line separation in the simplified
# source derivation so headings, paragraphs, and list items stay readable.
# Div is intentionally excluded — too ubiquitous in email layouts.
_BLOCK_TAGS_FOR_SIMPLIFIED_SOURCE = frozenset({
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "blockquote", "section", "article",
})

# Safety cap: fall back to text mode if there are more segments than this.
# Prevents token explosion and validation fragility on dense HTML bodies.
_MAX_TRANSLATABLE_SEGMENTS = 150

# Preflight degradation thresholds for clearly large/rich HTML bodies.
# When any single threshold is exceeded the route skips structured JSON
# translation entirely and proceeds directly to text fallback, avoiding
# the latency cost of an expensive structured call that will likely fail
# or timeout on dense newsletter-class emails.
_PREFLIGHT_MAX_HTML_CHARS = 30_000   # raw HTML character count
_PREFLIGHT_MAX_IMG_COUNT = 5         # <img elements (newsletter image density)
_PREFLIGHT_MAX_LINK_COUNT = 20       # href= attributes (CTA / nav link density)
_PREFLIGHT_MAX_TABLE_COUNT = 5       # <table elements (layout complexity)

# Chunked text-fallback thresholds.
# When body_text token count exceeds _FALLBACK_CHUNK_TOKEN_THRESHOLD the
# monolithic single-call fallback is replaced with sequential per-chunk calls,
# eliminating the server-side 502 / "Translation timed out" on large newsletter
# plain-text bodies (e.g. Supabase-class emails).
#
# Evidence basis:
#   - Mistral endpoint timeout observed on bodies >= ~1 500 tokens (plain text)
#   - 800 tokens/chunk keeps each call well within the safe-zone and leaves
#     enough output budget (max_tokens = chunk_tokens + 128, capped at 2 048)
#   - Decision is based solely on engine.count_tokens(), covering all scripts
_FALLBACK_CHUNK_TOKEN_THRESHOLD = 1_500   # tokens above which chunking is used
_FALLBACK_CHUNK_MAX_TOKENS = 800          # target max tokens per individual chunk
# Rate-limit resilience for chunked translation.
# Per-chunk bounded retry on provider 429 / rate-limit errors with exponential backoff.
# Delays: attempt 0→1: 1 s; attempt 1→2: 2 s.  Total extra wait ≤ 3 s per chunk.
# A small inter-chunk pause reduces burst rate-limit probability on dense chunks.
_CHUNK_RATE_LIMIT_MAX_RETRIES = 2  # max additional attempts per chunk on provider 429
_CHUNK_INTER_DELAY_S = 0.2         # inter-chunk pause (s) to reduce burst rate-limit risk

# Rich-body translation input budget.
# Applied after chrome removal to cap the translation input for preflight-degraded
# rich emails (e.g. Supabase-class newsletters with 17 000+ char bodies).
# 1 600 tokens → at most 2 chunks at 800 tokens/chunk (down from 7 in production).
_RICH_BODY_BUDGET_TOKENS = 1_600

# Block-level chrome patterns for rich-body canonicalization.
# Used in _is_chrome_block to detect footer/legal/social/delivery boilerplate.
# Conservative: the match alone is NOT sufficient — see _is_chrome_block for
# the residual substantive-word check that prevents mixed-content paragraphs
# from being classified as chrome.
_CHROME_BLOCK_RE = re.compile(
    r"\b(?:unsubscribe|opt[\s\-_]?out|"
    r"manage\s+(?:prefs?|subscriptions?|preferences)|"
    r"view\s+(?:in\s+)?(?:browser|online)|"
    r"mailing\s+address|"
    r"this\s+email\s+was\s+sent\s+to|"
    r"you\s+(?:are\s+receiving|received)\s+this\s+(?:email|newsletter|message)|"
    r"copyright\s+\d{4}|all\s+rights\s+reserved|"
    r"privacy\s+policy|terms\s+of\s+(?:service|use)|"
    r"connect\s+with\s+us|follow\s+us(?:\s+on)?|"
    r"©\s*\d{4}|"
    r"click\s+here\s+to\s+unsubscribe)\b",
    re.IGNORECASE,
)

# A paragraph is only classified as chrome when fewer than this many
# substantive words (len > 2) remain after the chrome keywords are removed.
# This prevents mixed-content paragraphs from being silently dropped.
_CHROME_BLOCK_MIN_SUBSTANTIVE_WORDS = 5

# Paragraphs at or below this character length are treated as section headers
# in score-based budgeting, giving them priority over longer body paragraphs.
_CONTENT_HEADER_MAX_CHARS = 80

# Maximum time (seconds) the interactive chunk path will wait for an active
# provider cooldown before proceeding. Prevents an interactive request from
# waiting indefinitely when the governor records a long backoff.
_CHUNK_MAX_COOLDOWN_WAIT_S = 30.0


def _is_chrome_block(para: str) -> bool:
    """
    Return True if a paragraph is chrome that adds no meaningful reading value.

    Three criteria (first two are always-chrome — no false-positive risk):
      1. Consists entirely of bare URLs (link-cloud): ≥2 raw URLs, nothing else.
      2. Is a separator-only line (dashes, equals, asterisks).
      3. Contains a strong footer/legal/social chrome keyword AND after removing
         all matched keyword phrases, fewer than _CHROME_BLOCK_MIN_SUBSTANTIVE_WORDS
         (len > 2) remain.  This residual-word check is what makes the classifier
         genuinely conservative: a paragraph such as
           "You can read more about our Privacy Policy in the help center."
         is NOT classified as chrome because ≥5 substantive words survive the
         keyword removal, whereas a pure boilerplate line like
           "Privacy Policy | Terms of Service"
         yields 0 substantive residual words and IS classified as chrome.
    """
    stripped = para.strip()
    if not stripped:
        return False
    # Always-chrome: no false-positive risk for these structural signals.
    if _LINK_CLOUD_LINE_RE.match(stripped):
        return True
    if _SEPARATOR_LINE_RE.match(stripped):
        return True
    # Chrome keyword present — apply residual substantive-word guard.
    if _CHROME_BLOCK_RE.search(stripped):
        residual = _CHROME_BLOCK_RE.sub("", stripped)
        substantive = [
            w for w in re.split(r"[\s|,;:\-/\\()\[\]{}]+", residual)
            if len(w) > 2
        ]
        if len(substantive) < _CHROME_BLOCK_MIN_SUBSTANTIVE_WORDS:
            return True
    return False


def _is_html_preflight_degraded(body_html: str) -> bool:
    """
    Deterministic preflight check for clearly large/rich HTML bodies.

    Returns True if the HTML complexity clearly exceeds reliable structured
    translation capacity.  All signals are computed on the raw HTML string
    (no parsing needed) for maximum speed in the hot request path.

    A single exceeded threshold is sufficient to trigger degradation —
    any one of these signals alone indicates a newsletter-class email:
      - raw HTML character count > _PREFLIGHT_MAX_HTML_CHARS (30 000)
      - image count (<img tags)  > _PREFLIGHT_MAX_IMG_COUNT  (5)
      - link count (href= attrs) > _PREFLIGHT_MAX_LINK_COUNT (20)
      - table count (<table tags)> _PREFLIGHT_MAX_TABLE_COUNT (5)

    Thresholds are set conservatively so a normal structured email
    (e.g. Google Security Alert) never triggers degradation.
    """
    if len(body_html) > _PREFLIGHT_MAX_HTML_CHARS:
        return True
    html_lower = body_html.lower()
    if html_lower.count("<img") > _PREFLIGHT_MAX_IMG_COUNT:
        return True
    if html_lower.count("href=") > _PREFLIGHT_MAX_LINK_COUNT:
        return True
    if html_lower.count("<table") > _PREFLIGHT_MAX_TABLE_COUNT:
        return True
    return False


def _should_chunk_fallback_translation(body_text: str, engine) -> bool:
    """
    Decide whether the text-fallback path should use chunked translation.

    Returns True when engine.count_tokens(body_text) exceeds
    _FALLBACK_CHUNK_TOKEN_THRESHOLD.

    Always uses the actual token count — no character-length fast-path.
    A character shortcut would silently skip chunking for dense-token bodies
    (e.g. CJK or other scripts where one character ≈ one token) that are
    short in bytes but large in tokens and would still timeout server-side.
    """
    return engine.count_tokens(body_text) > _FALLBACK_CHUNK_TOKEN_THRESHOLD


def _batch_within_budget(parts: List[str], joiner: str, engine) -> List[str]:
    """
    Greedily accumulate non-empty parts into joined batches within token budget.

    Token cost is summed per-part (not on the joined result), which
    intentionally undercounts joiner overhead — the token-verified prefix split
    in _hard_split_segment layer 4 absorbs any residual overrun by construction.
    A single part that individually exceeds the budget is emitted as a
    one-item batch so the caller's next layer can handle it.
    """
    batches: List[str] = []
    batch: List[str] = []
    batch_tokens: int = 0

    for part in parts:
        if not part:
            continue
        t = engine.count_tokens(part)
        if batch_tokens + t > _FALLBACK_CHUNK_MAX_TOKENS and batch:
            batches.append(joiner.join(batch))
            batch = [part]
            batch_tokens = t
        else:
            batch.append(part)
            batch_tokens += t

    if batch:
        batches.append(joiner.join(batch))

    return batches


def _token_verified_prefix_split(seg: str, engine) -> List[str]:
    """
    Split *seg* into token-verified chunks via binary-search prefix fitting.

    For each iteration the binary search finds the longest character prefix
    of the remaining string that satisfies:
        engine.count_tokens(prefix) <= _FALLBACK_CHUNK_MAX_TOKENS

    Complexity: O(log(len(seg))) count_tokens calls per emitted chunk —
    cheaper than a linear scan and guaranteed to converge regardless of how
    the tokeniser distributes tokens across character boundaries.

    Invariants enforced:
      - Every emitted chunk: count_tokens(chunk) <= _FALLBACK_CHUNK_MAX_TOKENS
      - Concatenation of all emitted chunks == seg (no text lost)
      - No empty chunks emitted
      - At least one character is consumed per iteration (loop always terminates)

    Called from _hard_split_segment layer 4 as the absolute last resort.
    Also used directly when the calling context needs a token-exact split.
    """
    if not seg:
        return []

    result: List[str] = []
    remaining = seg

    while remaining:
        if engine.count_tokens(remaining) <= _FALLBACK_CHUNK_MAX_TOKENS:
            result.append(remaining)
            break

        # Binary search for the longest prefix within budget.
        # Invariant: remaining[:lo] always fits; remaining[:hi+1] does not.
        # Upper-midpoint formula ((lo+hi+1)//2) prevents lo from stagnating.
        lo, hi = 1, len(remaining)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if engine.count_tokens(remaining[:mid]) <= _FALLBACK_CHUNK_MAX_TOKENS:
                lo = mid
            else:
                hi = mid - 1

        # lo is the longest prefix length guaranteed within budget.
        # Clamp to at least 1 to guarantee progress even when a single
        # character tokenises above the budget (pathological but safe).
        cut = max(1, lo)

        # Do not cut inside a [[PROT_N]] placeholder token.  The binary
        # search operates on raw character positions and can land mid-token
        # (e.g. splitting "[[PROT_0]]" into "[[PROT_" / "0]]").  Walk all
        # placeholder spans in the current window; if the cut falls inside
        # one, retract to the placeholder's start (keeping it whole in the
        # next chunk).  Use _ps > 0 guard: if the placeholder starts at 0
        # there is nowhere to retract — advance past the whole token instead.
        for _m in _PROTECTED_PLACEHOLDER_RE.finditer(remaining):
            _ps, _pe = _m.start(), _m.end()
            if _ps < cut < _pe:
                cut = _ps if _ps > 0 else _pe
                break

        result.append(remaining[:cut])
        remaining = remaining[cut:]

    return [r for r in result if r]


def _hard_split_segment(text: str, engine) -> List[str]:
    """
    Guarantee-bounded split for any text segment that exceeds
    _FALLBACK_CHUNK_MAX_TOKENS.

    Applies four progressively finer strategies in strict cascade.  At each
    layer, segments that fall within budget are moved to the result list;
    still-oversized segments carry forward to the next layer.  Order is
    always preserved — within each layer, segments are processed
    left-to-right and their sub-parts are emitted in order before the next
    segment is processed.

    Layer 1 — sentence boundaries (.!?)    most structure-preserving
    Layer 2 — line boundaries (\\n)        useful for lists / footers
    Layer 3 — word-group batching          whitespace-split words
    Layer 4 — token-verified prefix split  absolute last resort:
               binary-search on character prefix length; every emitted
               chunk is token-bounded by construction via
               engine.count_tokens() verification, regardless of
               tokeniser density (CJK, URL blobs, base64, etc.)

    Guarantees: at least one result; no text lost; no empty chunks emitted;
    every emitted chunk satisfies count_tokens(chunk) <= _FALLBACK_CHUNK_MAX_TOKENS.
    """
    if engine.count_tokens(text) <= _FALLBACK_CHUNK_MAX_TOKENS:
        return [text]

    done: List[str] = []
    pending: List[str] = [text]

    # Layer 1: sentence boundaries
    next_pending: List[str] = []
    for seg in pending:
        if engine.count_tokens(seg) <= _FALLBACK_CHUNK_MAX_TOKENS:
            done.append(seg)
            continue
        for b in _batch_within_budget(re.split(r"(?<=[.!?])\s+", seg), " ", engine):
            if engine.count_tokens(b) <= _FALLBACK_CHUNK_MAX_TOKENS:
                done.append(b)
            else:
                next_pending.append(b)
    pending = next_pending

    # Layer 2: line boundaries
    next_pending = []
    for seg in pending:
        lines = [ln for ln in seg.splitlines() if ln.strip()]
        if not lines:
            done.append(seg) if seg.strip() else None
            continue
        for b in _batch_within_budget(lines, "\n", engine):
            if engine.count_tokens(b) <= _FALLBACK_CHUNK_MAX_TOKENS:
                done.append(b)
            else:
                next_pending.append(b)
    pending = next_pending

    # Layer 3: word-group batching
    next_pending = []
    for seg in pending:
        words = seg.split()
        if not words:
            done.append(seg) if seg else None
            continue
        for b in _batch_within_budget(words, " ", engine):
            if engine.count_tokens(b) <= _FALLBACK_CHUNK_MAX_TOKENS:
                done.append(b)
            else:
                next_pending.append(b)
    pending = next_pending

    # Layer 4: token-verified prefix split — absolute last resort.
    # Binary-search prefix fitting guarantees every emitted chunk satisfies
    # engine.count_tokens(chunk) <= _FALLBACK_CHUNK_MAX_TOKENS by construction,
    # regardless of tokeniser density (CJK, URL blobs, base64, etc.).
    for seg in pending:
        done.extend(_token_verified_prefix_split(seg, engine))

    return [s for s in done if s] or [text]


def _split_text_into_translation_chunks(body_text: str, engine) -> List[str]:
    """
    Split plain text into bounded, paragraph-preserving chunks for sequential
    translation.

    Strategy (in priority order):
      1. Split on blank-line boundaries (\\n\\n+) — preserves reading structure.
      2. Accumulate consecutive paragraphs into one chunk until the token
         budget (_FALLBACK_CHUNK_MAX_TOKENS) is reached, then flush.
      3. If a single paragraph individually exceeds the budget, delegate to
         _hard_split_segment which applies sentence → line → word →
         token-verified prefix split in cascade, guaranteeing all emitted
         segments are bounded.

    Returns at least one chunk.  Order is always preserved.
    """
    raw_paras = re.split(r"\n\n+", body_text)
    paragraphs = [p.strip() for p in raw_paras if p.strip()]

    chunks: List[str] = []
    current_parts: List[str] = []
    current_tokens: int = 0

    for para in paragraphs:
        para_tokens = engine.count_tokens(para)

        if para_tokens > _FALLBACK_CHUNK_MAX_TOKENS:
            # Flush current accumulator before handling the oversized paragraph.
            if current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_tokens = 0

            # Hard-fallback split guarantees all emitted segments are bounded.
            chunks.extend(_hard_split_segment(para, engine))

        elif current_tokens + para_tokens > _FALLBACK_CHUNK_MAX_TOKENS:
            # Budget exceeded — flush and start a new accumulator.
            if current_parts:
                chunks.append("\n\n".join(current_parts))
            current_parts = [para]
            current_tokens = para_tokens

        else:
            current_parts.append(para)
            current_tokens += para_tokens

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks if chunks else [body_text]


def _is_rate_limit_error(exc: Exception) -> bool:
    """
    Deterministic check: True when exc signals a provider rate-limit (HTTP 429).

    Inspects the stringified exception for signals emitted by the engine wrapper
    (MistralEngine.generate_text_async raises RuntimeError whose message contains
    the HTTP status code or "Too Many Requests" / "rate limit" text).
    Conservative: only returns True for known 429-class signals.
    """
    msg = str(exc).lower()
    return (
        "429" in msg
        or "too many requests" in msg
        or "rate limit" in msg
        or "rate_limit" in msg
    )


async def _translate_text_chunks_async(
    chunks: List[str],
    target_language: str,
    engine,
    system_prompt: str,
) -> str:
    """
    Translate each chunk sequentially and reassemble in the original order.

    Sequential (not concurrent) to avoid parallel timeout pressure and to
    guarantee deterministic ordering of translated segments.  Each chunk gets
    its own bounded max_tokens estimate so no single call overshoots the
    model's safe output window.

    Rate-limit resilience: each chunk is retried up to _CHUNK_RATE_LIMIT_MAX_RETRIES
    times on provider 429 / rate-limit errors.  After recording the rate limit in
    the governor, the retry wait uses the governor's effective cooldown remaining
    (floor 1 s, cap _CHUNK_MAX_COOLDOWN_WAIT_S) so intra-chunk retries respect the
    same backpressure signal as the pre-chunk adaptive wait — not a fixed 1 s/2 s.
    Non-rate-limit exceptions propagate immediately without retry.

    Adaptive backpressure: before each chunk attempt the governor cooldown is
    checked.  If a provider cooldown is active (from an earlier 429 in this or
    any concurrent request), the chunk waits for the shorter of the remaining
    cooldown and _CHUNK_MAX_COOLDOWN_WAIT_S before proceeding.  This makes
    chunk pacing adaptive rather than fixed, reducing successive 429 cascades
    on high-chunk requests.

    A minimum inter-chunk pause (_CHUNK_INTER_DELAY_S) is always applied after
    each completed chunk (except the last) regardless of the cooldown wait.

    Returns a single paragraph-spaced string with empty parts filtered out.
    """
    translated_parts: List[str] = []
    gov = _get_mistral_governor()
    for chunk_idx, chunk in enumerate(chunks):
        # Adaptive backpressure: respect any active provider cooldown before
        # attempting this chunk.  Capped at _CHUNK_MAX_COOLDOWN_WAIT_S so
        # interactive requests are never indefinitely stalled.
        cooldown_remaining = gov.get_cooldown_remaining()
        if cooldown_remaining > 0:
            adaptive_wait = min(cooldown_remaining, _CHUNK_MAX_COOLDOWN_WAIT_S)
            logger.info(
                "[TRANSLATE-RENDER] chunk_cooldown_wait chunk=%d wait=%.1fs",
                chunk_idx, adaptive_wait,
            )
            await asyncio.sleep(adaptive_wait)

        estimated_tokens = max(256, min(2048, engine.count_tokens(chunk) + 128))
        translated_chunk: Optional[str] = None
        for attempt in range(_CHUNK_RATE_LIMIT_MAX_RETRIES + 1):
            try:
                translated_chunk = await engine.generate_text_async(
                    prompt=(
                        f"Target language: {target_language}\n\n"
                        f"Email body:\n{chunk}"
                    ),
                    max_tokens=estimated_tokens,
                    temperature=0.2,
                    system_prompt=system_prompt,
                )
                break
            except Exception as exc:
                if _is_rate_limit_error(exc) and attempt < _CHUNK_RATE_LIMIT_MAX_RETRIES:
                    gov.record_rate_limit()
                    retry_wait = max(
                        1.0, min(gov.get_cooldown_remaining(), _CHUNK_MAX_COOLDOWN_WAIT_S)
                    )
                    logger.warning(
                        "[TRANSLATE-RENDER] chunk_rate_limit chunk=%d attempt=%d/%d wait=%.1fs",
                        chunk_idx, attempt + 1, _CHUNK_RATE_LIMIT_MAX_RETRIES, retry_wait,
                    )
                    await asyncio.sleep(retry_wait)
                else:
                    raise
        translated_parts.append((translated_chunk or "").strip())
        if chunk_idx < len(chunks) - 1:
            await asyncio.sleep(_CHUNK_INTER_DELAY_S)

    return "\n\n".join(p for p in translated_parts if p)


def _is_hidden_element(element) -> bool:
    """
    Return True if the element is clearly hidden or non-user-visible.

    Detects the dominant email preheader hiding patterns and common CSS hide
    techniques. Only narrow, evidence-backed heuristics — no broad false-positive risk.
    Checked against every ancestor in _collect_translatable_nodes so that
    nested text inside a hidden container is also excluded.
    """
    if not hasattr(element, "get"):
        return False
    style = (element.get("style") or "").strip()
    if style and _HIDDEN_STYLE_PATTERNS.search(style):
        return True
    classes = element.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    if classes and _HIDDEN_CLASS_ID_PATTERN.search(" ".join(classes)):
        return True
    elem_id = (element.get("id") or "").strip()
    if elem_id and _HIDDEN_CLASS_ID_PATTERN.search(elem_id):
        return True
    return False


def _is_noise_element_for_simplified_source(element) -> bool:
    """
    Conservative noise filter for the simplified fallback source derivation.
    Flags elements with explicit footer/social/unsubscribe class or ID only.
    """
    if not hasattr(element, "get"):
        return False
    classes = element.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    if classes and _SIMPLIFIED_NOISE_CLASS_ID_RE.search(" ".join(classes)):
        return True
    elem_id = (element.get("id") or "").strip()
    if elem_id and _SIMPLIFIED_NOISE_CLASS_ID_RE.search(elem_id):
        return True
    return False


def _derive_fallback_source_impl(
    body_html: str,
    *,
    protect_mode: bool,
) -> Tuple[str, Dict[str, str]]:
    """
    Shared derivation engine for the simplified fallback source pipeline.

    Both public helpers delegate here; the only behavioral difference is
    controlled by protect_mode:

      protect_mode=False  (unwrap mode)
        Layer 3 unwraps translate="no" / class="notranslate" elements so
        their visible text flows into the translation stream.  Useful when
        the model should translate surrounding context and can see the
        protected values verbatim.

      protect_mode=True   (placeholder mode)
        Layer 3 replaces each protected element with a [[PROT_N]] token and
        records the original visible text in placeholder_map.  The map is
        returned so the caller can restore the originals after translation.
        When protect_mode=False the returned map is always {}.

    Layers (applied in order):
      1. Hidden/preheader elements (CSS hiding, mso-hide, preheader class/ID)
         — decomposed.
      2. Footer/social/unsubscribe containers (class/ID pattern match)
         — decomposed.
      3. Non-translatable markers (translate="no" / class="notranslate")
         — unwrapped (unwrap mode) or token-replaced (placeholder mode).
      4. Meaningful content-link destinations injected inline:
           http/https -> "Label (https://...)"
           mailto:    -> "Label (address@example.com)"
           tel:       -> "Label (+123456789)"
         Compact rule: label == destination omits the parenthetical.
         Fragment (#) and href-less anchors become plain text.
      5. Block-level elements surrounded by blank-line markers for readable
         paragraph/heading separation.

    Returns ("", {}) when BS4 is unavailable.
    """
    if not _BS4_AVAILABLE:
        return "", {}
    soup = _BeautifulSoup(body_html, "html.parser")
    placeholder_map: Dict[str, str] = {}

    # Layer 1: hidden / preheader
    for tag in list(soup.find_all(True)):
        if tag.parent is not None and _is_hidden_element(tag):
            tag.decompose()

    # Layer 2: footer / social / unsubscribe noise
    for tag in list(soup.find_all(True)):
        if tag.parent is not None and _is_noise_element_for_simplified_source(tag):
            tag.decompose()

    # Layer 3: non-translatable markers
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        is_protected = tag.get("translate") == "no"
        if not is_protected:
            classes = tag.get("class") or []
            if isinstance(classes, str):
                classes = classes.split()
            is_protected = any(c.lower() == "notranslate" for c in classes)
        if not is_protected:
            continue
        if protect_mode:
            visible_text = tag.get_text(separator=" ", strip=True)
            if visible_text:
                token = f"[[PROT_{len(placeholder_map)}]]"
                placeholder_map[token] = visible_text
                tag.replace_with(token)
            else:
                tag.decompose()
        else:
            tag.unwrap()

    # Layer 4: inject content-link destinations inline
    for a_tag in list(soup.find_all("a")):
        if a_tag.parent is None:
            continue
        href = str(a_tag.get("href") or "").strip()
        label = a_tag.get_text(strip=True)
        if not label:
            continue
        if href.startswith(("http://", "https://")):
            dest = href
            a_tag.replace_with(label if label == dest else f"{label} ({dest})")
        elif href.startswith("mailto:"):
            dest = href[len("mailto:"):].split("?")[0].strip()
            a_tag.replace_with(label if label == dest else f"{label} ({dest})")
        elif href.startswith("tel:"):
            dest = href[len("tel:"):].strip()
            a_tag.replace_with(label if label == dest else f"{label} ({dest})")

    # Layer 5: blank-line markers around block elements
    for tag in list(soup.find_all(list(_BLOCK_TAGS_FOR_SIMPLIFIED_SOURCE))):
        if tag.parent is not None:
            tag.insert_before("\n\n")
            tag.insert_after("\n\n")

    raw = soup.get_text(separator="\n")
    lines = [line.rstrip() for line in raw.splitlines()]
    normalized = _MULTI_BLANK_LINE_RE.sub("\n\n", "\n".join(lines))
    return normalized.strip(), placeholder_map


def _derive_simplified_fallback_source(body_html: str) -> str:
    """
    Derive clean visible-order plain-text source from rich HTML (unwrap mode).

    Protected elements (translate="no" / class="notranslate") are unwrapped
    so their visible text flows into the translation stream.  All other
    suppression, link-annotation, and structure layers are applied identically
    to _derive_protected_fallback_source.

    Returns "" when BS4 is unavailable or extraction yields nothing.
    """
    result, _ = _derive_fallback_source_impl(body_html, protect_mode=False)
    return result


def _derive_protected_fallback_source(
    body_html: str,
) -> Tuple[str, Dict[str, str]]:
    """
    Derive the simplified fallback source with placeholder-token substitution.

    Protected elements (translate="no" / class="notranslate") are replaced
    with deterministic [[PROT_N]] tokens; the original visible text is
    returned in placeholder_map so it can be restored after translation via
    _restore_protected_tokens.

    Returns ("", {}) when BS4 is unavailable.
    """
    return _derive_fallback_source_impl(body_html, protect_mode=True)


def _restore_protected_tokens(text: str, placeholder_map: Dict[str, str]) -> str:
    """
    Restore placeholder tokens inserted by _derive_protected_fallback_source.

    For each [[PROT_N]] token in placeholder_map, replaces its occurrence in
    text with the original visible content.

    Conservative fallback: if a token is absent from text (the model dropped
    it) or was mangled beyond simple string matching, the replacement is a
    no-op — the translated text is returned as-is for that token.  This
    avoids injecting protected content at an incorrect position.
    """
    for token, original in placeholder_map.items():
        text = text.replace(token, original)
    return text


def _should_prefer_simplified_source(
    existing_body_text: str, derived_source: str
) -> bool:
    """
    Conservative guard: returns True only when the derived simplified source
    is plausibly a better translation input than the existing body_text.

    Two conditions must both hold:
      1. Substance: derived_source has at least _SIMPLIFIED_SOURCE_MIN_CHARS
         non-empty characters — trivially short extractions are rejected.
      2. Compression: derived_source is shorter than
         existing_body_text * _SIMPLIFIED_SOURCE_MAX_RATIO — the HTML
         noise removal must have materially reduced the content, not
         expanded it.  A derived source that is equal to or larger than
         the existing body signals that extraction inflated rather than
         cleaned the content.

    Special case: when existing_body_text is empty the derived source
    is always preferred (provided it passes the substance check).
    """
    if len(derived_source) < _SIMPLIFIED_SOURCE_MIN_CHARS:
        return False
    if not existing_body_text:
        return True
    return len(derived_source) < len(existing_body_text) * _SIMPLIFIED_SOURCE_MAX_RATIO


def _score_source_noise(text: str) -> float:
    """
    Deterministic noise penalty for a translation source candidate.

    Returns 0.0 for clean canonical text; higher values signal noisier content.

    Penalty signals (additive):
      +5.0 per line containing footer/social/unsubscribe markers
      +20.0 * (link_cloud_lines / total_lines) for URL-only line density
      +2.0 per separator-only line (dashes, equals, asterisks)
      +4.0 per duplicate paragraph fingerprint (first 120 normalised chars)
    """
    if not text:
        return 0.0
    lines = text.splitlines()
    total_lines = max(len(lines), 1)
    penalty = 0.0

    footer_lines = sum(1 for ln in lines if _FOOTER_NOISE_SIGNAL_RE.search(ln))
    penalty += footer_lines * 5.0

    link_cloud = sum(
        1 for ln in lines if ln.strip() and _LINK_CLOUD_LINE_RE.match(ln)
    )
    penalty += (link_cloud / total_lines) * 20.0

    sep_lines = sum(1 for ln in lines if _SEPARATOR_LINE_RE.match(ln))
    penalty += sep_lines * 2.0

    paras = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    seen: set = set()
    for p in paras:
        key = re.sub(r"\s+", " ", p[:120]).lower()
        if key in seen:
            penalty += 4.0
        seen.add(key)

    return penalty


def _select_canonical_translation_source(
    existing_body_text: str,
    derived_source: str,
) -> Tuple[bool, str]:
    """
    Canonical-source selector for the preflight-degraded rich-email lane.

    Returns (prefer_derived, reason_label).

    prefer_derived=False  existing_body_text is the canonical base.
    prefer_derived=True   derived_source is materially better.

    Selection rules (in priority order):
      1. derived_source empty / below minimum substance
         → False ("derived_empty")
      2. existing_body_text empty
         → True ("body_text_empty")
      3. body_text clearly cleaner (noise_gap > _NOISE_GAP_CANONICAL_PREFERENCE)
         → False ("body_text_canonical")
      4. derived materially shorter (noise scores similar, old criterion)
         → True ("derived_shorter")
      5. Default
         → False ("body_text_canonical")
    """
    if not derived_source or len(derived_source) < _SIMPLIFIED_SOURCE_MIN_CHARS:
        return False, "derived_empty"
    if not existing_body_text:
        return True, "body_text_empty"

    body_noise = _score_source_noise(existing_body_text)
    derived_noise = _score_source_noise(derived_source)

    if body_noise + _NOISE_GAP_CANONICAL_PREFERENCE <= derived_noise:
        return False, "body_text_canonical"

    if len(derived_source) < len(existing_body_text) * _SIMPLIFIED_SOURCE_MAX_RATIO:
        return True, "derived_shorter"

    return False, "body_text_canonical"


def _enrich_body_text_with_assists(
    body_text: str,
    derived_source: str,
) -> str:
    """
    Controlled enrichment: appends meaningful URLs from the HTML-derived source
    that are absent from the canonical body_text.

    Only URLs found on non-footer lines of derived_source are considered.
    Duplicate URLs (already present in body_text) are skipped.
    Does NOT reorder body_text or inject sections.
    Returns body_text unchanged when no meaningful URLs are missing.
    """
    if not derived_source or not body_text:
        return body_text

    _URL_RE = re.compile(r"https?://\S+")

    def _norm_url(u: str) -> str:
        return u.rstrip(")>].,;\"'")

    existing_urls: set = set(_norm_url(u) for u in _URL_RE.findall(body_text))
    assist_urls: List[str] = []
    seen_assist: set = set()

    for line in derived_source.splitlines():
        if _FOOTER_NOISE_SIGNAL_RE.search(line):
            continue
        for url in _URL_RE.findall(line):
            norm = _norm_url(url)
            if norm not in existing_urls and norm not in seen_assist:
                assist_urls.append(norm)
                seen_assist.add(norm)

    if not assist_urls:
        return body_text

    return body_text.rstrip() + "\n\n" + "\n".join(assist_urls)


def _trim_footer_tail(text: str) -> str:
    """
    Conservative tail-trim: cuts an obvious footer/social/unsubscribe region
    from the bottom of a translated newsletter body.

    Only triggers when ALL conditions hold:
      - At least 5 lines total.
      - At least 3 footer-signal lines in the last 35% of lines.
      - The retained head is at least 200 characters.

    Returns the original text unchanged when conditions are not met.
    """
    if not text:
        return text
    lines = text.splitlines()
    n = len(lines)
    if n < 5:
        return text

    scan_start = max(0, int(n * 0.65))
    tail_lines = lines[scan_start:]

    footer_indices = [
        i for i, ln in enumerate(tail_lines)
        if _FOOTER_NOISE_SIGNAL_RE.search(ln)
    ]
    if len(footer_indices) < 3:
        return text

    cut_abs = scan_start + footer_indices[0]
    while cut_abs > 0 and lines[cut_abs - 1].strip():
        cut_abs -= 1

    head = "\n".join(lines[:cut_abs]).rstrip()
    if len(head) < 200:
        return text

    return head


def _dedup_repeated_blocks(text: str) -> str:
    """
    Deterministic repeated-block deduplication for newsletter-class simplified outputs.

    Splits at paragraph boundaries (\\n\\n+), normalises each block's fingerprint
    (first 120 lowercased, whitespace-collapsed characters), and keeps only the
    first occurrence. Canonical order is preserved.
    """
    if not text:
        return text
    paras = re.split(r"\n\n+", text)
    seen: set = set()
    unique: List[str] = []
    for p in paras:
        stripped = p.strip()
        if not stripped:
            continue
        key = re.sub(r"\s+", " ", stripped[:120]).lower()
        if key not in seen:
            seen.add(key)
            unique.append(stripped)
    return "\n\n".join(unique)


def _normalize_canonical_body_pre_translation(text: str) -> str:
    """
    Conservative pre-translation normalization of canonical plain-text body.

    Applied in the structured_preflight_degraded lane BEFORE source selection
    and translation so that footer/social/unsubscribe tail and link-cloud
    residue are removed from the canonical candidate before it enters the
    chunk-size decision and translation prompt.

    Steps applied in order (each is conservative and a no-op when not triggered):
      1. Footer-tail trim — cuts obvious footer/social/unsubscribe tail via
         the same bounded heuristic as _trim_footer_tail (>= 3 signals in the
         last 35% of lines; retained head >= 200 chars).
      2. Link-cloud collapse — removes lines that consist entirely of bare URLs
         (social icon / button clusters invisible in plain-text clients).
      3. Blank-line normalization — collapses runs of 3+ blank lines to one.
      4. Repeated-block dedup — removes duplicate paragraphs via fingerprint match.

    Preserves legitimate newsletter sections (announcements, highlights, jobs)
    because they do not match footer-signal or link-cloud patterns.
    Returns the original text unchanged when it is empty or already clean.
    """
    if not text:
        return text
    text = _trim_footer_tail(text)
    lines = text.splitlines()
    cleaned = [ln for ln in lines if not (ln.strip() and _LINK_CLOUD_LINE_RE.match(ln))]
    text = _MULTI_BLANK_LINE_RE.sub("\n\n", "\n".join(cleaned)).strip()
    text = _dedup_repeated_blocks(text)
    return text


def _budget_rich_body_for_translation(text: str, engine) -> str:
    """
    Deterministic section-coherent canonicalization and token budgeting for
    rich preflight-degraded email bodies.

    Applied in the structured_preflight_degraded lane as the primary pre-
    translation cleanup, replacing the plain _normalize_canonical_body_pre_translation
    call with a stronger three-stage pipeline:

      Stage 1 — Normalization
        Delegates to _normalize_canonical_body_pre_translation (footer-tail trim,
        link-cloud collapse, blank-line normalization, repeated-block dedup).

      Stage 2 — Chrome removal
        Splits at paragraph boundaries and removes blocks whose entire text is
        chrome: footer/legal/social/receipt signals, link-cloud lines, separators.
        Preserves meaningful sections (product updates, community, jobs, events)
        because they do not match chrome patterns.

      Stage 3 — Section-coherent unit selection within token budget
        Groups content paragraphs into section units: a short paragraph
        (≤ _CONTENT_HEADER_MAX_CHARS) that follows a prior unit opens a new
        unit; its following body paragraphs belong to that unit.  A header
        must remain attached to its following body when both fit — no
        header-skeleton-only output when the budget allows including body text.
        Score: 2.0 for header-led units, 1.0 for body-only units.
        Units are selected in score-descending order (stable within equal
        scores → original document order preserved within each tier), ensuring
        that late meaningful section headers (e.g. "Jobs at Supabase",
        "Community Highlights") survive even when earlier verbose units would
        exhaust the budget under top-first selection.
        Bounded fallback for oversized units: when a unit's total tokens exceed
        the remaining budget, include its leading paragraphs greedily until the
        budget is full — a single unit can never blow the budget.
        Selected paragraphs are always emitted in their original document order.

    Does NOT reorder, summarize, or merge paragraphs.
    Returns the original text unchanged only when it is empty.
    On any unexpected error, returns the Stage-1 result as a safe fallback.
    """
    if not text:
        return text

    # Stage 1: existing normalization
    stage1 = _normalize_canonical_body_pre_translation(text)
    raw_chars = len(stage1)

    try:
        # Stage 2: block-level chrome removal
        paras = [p.strip() for p in re.split(r"\n\n+", stage1) if p.strip()]
        content_paras = [p for p in paras if not _is_chrome_block(p)]
        post_chrome_chars = sum(len(p) for p in content_paras)

        # Stage 3: section-coherent unit selection within token budget.
        # Group content paragraphs into section units: a short paragraph
        # (≤ _CONTENT_HEADER_MAX_CHARS) following a prior unit starts a new
        # unit; its following body paragraphs belong to it.  Selecting a unit
        # selects header + body together — no header-skeleton-only output when
        # the budget allows including body content.
        # Score: 2.0 for header-led units, 1.0 for body-only units.
        # Bounded fallback: oversized units include leading paragraphs that fit
        # so the budget is strictly respected.
        grouped: list = []
        current_group: list = []
        for ci, para in enumerate(content_paras):
            if len(para) <= _CONTENT_HEADER_MAX_CHARS and current_group:
                grouped.append(current_group)
                current_group = [(ci, para)]
            else:
                current_group.append((ci, para))
        if current_group:
            grouped.append(current_group)

        unit_data = []  # (group, score, total_tokens)
        for group in grouped:
            score = 2.0 if len(group[0][1]) <= _CONTENT_HEADER_MAX_CHARS else 1.0
            total_toks = sum(engine.count_tokens(p) for _, p in group)
            unit_data.append((group, score, total_toks))

        # Stable sort by score descending; within same score, original unit order.
        sorted_unit_indices = sorted(
            range(len(unit_data)), key=lambda u: -unit_data[u][1]
        )

        selected_para_indices: set = set()
        running_tokens = 0
        for u_idx in sorted_unit_indices:
            group, _score, unit_tokens = unit_data[u_idx]
            remaining = _RICH_BODY_BUDGET_TOKENS - running_tokens
            if remaining <= 0:
                continue
            if unit_tokens <= remaining:
                for ci, _ in group:
                    selected_para_indices.add(ci)
                running_tokens += unit_tokens
            else:
                # Bounded within-unit fallback: include leading paragraphs that fit.
                fallback_tokens = 0
                for ci, para in group:
                    para_toks = engine.count_tokens(para)
                    if fallback_tokens + para_toks <= remaining:
                        selected_para_indices.add(ci)
                        fallback_tokens += para_toks
                    else:
                        break
                running_tokens += fallback_tokens

        # Emit in original document order.
        kept = [content_paras[i] for i in sorted(selected_para_indices)]
        result = "\n\n".join(kept)
        post_budget_chars = len(result)

        logger.info(
            "[TRANSLATE-RENDER] rich_body_budget "
            "raw_chars=%d post_chrome_chars=%d post_budget_chars=%d "
            "budget_tokens=%d used_tokens=%d paras_kept=%d/%d",
            raw_chars,
            post_chrome_chars,
            post_budget_chars,
            _RICH_BODY_BUDGET_TOKENS,
            running_tokens,
            len(kept),
            len(paras),
        )

        return result if result else stage1
    except Exception:
        return stage1


def _derive_plain_text_from_html(html: str) -> str:
    """
    Extract clean, normalized plain text from translated HTML.

    Used to populate translated_body_text in the structured_html path.
    Two hardening steps beyond a raw get_text call:
      1. Hidden/preheader elements are removed before extraction so they
         cannot leak into the plain-text field.
      2. Excessive blank lines (3+) are collapsed to at most one blank line,
         preventing the blank-line inflation that get_text(separator="\\n")
         can produce on dense HTML bodies.
    """
    soup = _BeautifulSoup(html, "html.parser")
    for tag in list(soup.find_all(True)):
        if tag.parent is not None and _is_hidden_element(tag):
            tag.decompose()
    raw = soup.get_text(separator="\n")
    lines = [line.rstrip() for line in raw.splitlines()]
    normalized = _MULTI_BLANK_LINE_RE.sub("\n\n", "\n".join(lines))
    return normalized.strip()


def _collect_translatable_nodes(soup) -> List:
    """
    Walk the parse tree in document order and return NavigableString objects
    that represent visible, non-whitespace text eligible for translation.

    Exclusion rules (checked against every ancestor):
      - Nodes inside _HTML_SKIP_TAGS subtrees (script, style, etc.)
      - Nodes inside hidden/preheader elements (_is_hidden_element)
    """
    root = getattr(soup, "body", None) or soup
    nodes = []
    for element in root.descendants:
        if not isinstance(element, _NavigableString):
            continue
        if not str(element).strip():
            continue
        skip = False
        parent = element.parent
        while parent and hasattr(parent, "name"):
            if parent.name in _HTML_SKIP_TAGS:
                skip = True
                break
            if _is_hidden_element(parent):
                skip = True
                break
            parent = getattr(parent, "parent", None)
        if not skip:
            nodes.append(element)
    return nodes


def _build_structured_translation_system_prompt(target_language: str) -> str:
    target_label = get_translation_label(target_language)
    return (
        f"You are a professional email translator. Translate text segments into {target_label}.\n\n"
        "You will receive a JSON object with a \"segments\" array of text strings extracted "
        "from an email HTML body in document order. Return a JSON object with a single "
        "\"segments\" key containing an array of translated strings.\n\n"
        "Rules:\n"
        "- Output array MUST contain exactly the same number of strings as the input array.\n"
        "- Translate segments in the same order as the input — do not merge, split, or reorder.\n"
        "- Preserve URLs, email addresses, phone numbers, dates, times, codes, and reference "
        "numbers exactly unless surrounding prose requires inflection.\n"
        "- Preserve the professional tone and intent faithfully.\n"
        "- Return only the JSON object — no commentary and no markdown fences."
    )


async def _attempt_structured_html_translation(
    body_html: str,
    target_language: str,
    engine,
) -> Tuple[Optional[str], str]:
    """
    Attempt to translate body_html while preserving its HTML structure.

    Strategy:
      1. Parse HTML with BeautifulSoup.
      2. Collect visible text nodes in document order.
      3. Send segments to the model as a JSON array; request same-length JSON array back.
      4. Validate exact segment count match and string types.
      5. Reinsert translated text into a fresh parse of the original HTML.
      6. Serialize and return the translated HTML body content.

    Returns (translated_html, reason_code). On success: (html_string, "structured_success").
    On any failure: (None, reason_code) — the caller decides to fall back.
    All exceptions are caught internally; the caller's outer try handles unexpected raises.
    """
    if not _BS4_AVAILABLE:
        return None, "bs4_unavailable"

    soup = _BeautifulSoup(body_html, "html.parser")
    node_refs = _collect_translatable_nodes(soup)

    if not node_refs:
        return None, "no_translatable_nodes"

    if len(node_refs) > _MAX_TRANSLATABLE_SEGMENTS:
        logger.warning(
            "[TRANSLATE-RENDER] Segment count %d exceeds cap %d — falling back to text mode",
            len(node_refs),
            _MAX_TRANSLATABLE_SEGMENTS,
        )
        return None, "segment_cap_exceeded"

    input_segments = [str(n) for n in node_refs]
    total_chars = sum(len(s) for s in input_segments)
    # Allow generous output budget: translated text can be longer than source
    estimated_output_tokens = max(512, min(8192, total_chars // 3 + 512))

    prompt = (
        f"Translate the following {len(input_segments)} text segments into "
        f"{get_translation_label(target_language)}.\n\n"
        f"{json.dumps({'segments': input_segments}, ensure_ascii=False)}"
    )

    try:
        result = await engine.generate_json_async(
            prompt=prompt,
            max_tokens=estimated_output_tokens,
            temperature=0.1,
            system_prompt=_build_structured_translation_system_prompt(target_language),
        )
    except Exception as exc:
        logger.warning(
            "[TRANSLATE-RENDER] JSON translation call failed (%s) — falling back",
            type(exc).__name__,
        )
        return None, "json_translation_failed"

    if not isinstance(result, dict):
        logger.warning("[TRANSLATE-RENDER] Response is not a dict — falling back")
        return None, "response_not_dict"

    translated_segments = result.get("segments")
    if not isinstance(translated_segments, list):
        logger.warning("[TRANSLATE-RENDER] Response missing 'segments' list — falling back")
        return None, "segments_missing"

    if len(translated_segments) != len(input_segments):
        logger.warning(
            "[TRANSLATE-RENDER] Segment count mismatch: expected %d got %d — falling back",
            len(input_segments),
            len(translated_segments),
        )
        return None, "segment_count_mismatch"

    if not all(isinstance(s, str) for s in translated_segments):
        logger.warning("[TRANSLATE-RENDER] Non-string segment in response — falling back")
        return None, "non_string_segment"

    # Re-parse original HTML for mutation (avoids stale descriptor state)
    soup2 = _BeautifulSoup(body_html, "html.parser")
    node_refs2 = _collect_translatable_nodes(soup2)

    if len(node_refs2) != len(input_segments):
        logger.warning(
            "[TRANSLATE-RENDER] Node re-collection mismatch (%d vs %d) — falling back",
            len(node_refs2),
            len(input_segments),
        )
        return None, "node_recollection_mismatch"

    for node, translated_text in zip(node_refs2, translated_segments):
        node.replace_with(_NavigableString(translated_text))

    root = getattr(soup2, "body", None) or soup2
    return root.decode_contents(), "structured_success"


@app.get("/api/preferences/languages")
async def list_supported_languages():
    """Return supported AI output languages for frontend selectors."""
    return [
        {"code": code, "label": info["label"], "native": info["native"]}
        for code, info in SUPPORTED_LANGUAGES.items()
    ]


@api_router.get("/tones")
async def list_tones():
    """Return supported draft tones for authenticated compose flows."""
    return list_supported_tones()


@api_router.get("/templates")
async def list_templates(account_id: str, language: str = Query("en")):
    """
    List templates for an account filtered by the active language plus neutral templates.
    """
    store = safe_get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Storage unavailable")

    effective_account_id = resolve_account_id(None, account_id)
    requested_language = (language or "en").strip()

    if requested_language.lower() == "neutral":
        language_filter = ["neutral"]
    else:
        normalized_language = normalize_language(requested_language)
        if (
            normalized_language == DEFAULT_LANGUAGE
            and requested_language.lower() not in {
                k.lower() for k in SUPPORTED_LANGUAGES
            }
            and requested_language.lower() != DEFAULT_LANGUAGE
        ):
            raise HTTPException(status_code=400, detail="Unsupported language")
        language_filter = [normalized_language, "neutral"]

    try:
        result = await asyncio.to_thread(
            lambda: store.client.table("email_templates")
            .select("*")
            .eq("account_id", effective_account_id)
            .in_("language", language_filter)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"[TEMPLATES] List failed for {effective_account_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load templates")


@api_router.post("/templates")
async def create_template(request: TemplateCreateRequest):
    """
    Create a reusable email template for one account.
    """
    store = safe_get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Storage unavailable")

    effective_account_id = resolve_account_id(None, request.account_id)
    name = (request.name or "").strip()
    body = (request.body or "").strip()
    requested_tone = (request.tone or "professional").strip().lower()
    requested_language = (request.language or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Template name is required")

    if not body:
        raise HTTPException(status_code=400, detail="Template body is required")

    if requested_tone not in SUPPORTED_TONES:
        raise HTTPException(status_code=400, detail="Unsupported tone")

    if requested_language.lower() == "neutral":
        stored_language = "neutral"
    else:
        normalized_language = normalize_language(requested_language)
        if (
            normalized_language == DEFAULT_LANGUAGE
            and requested_language.lower() not in {
                k.lower() for k in SUPPORTED_LANGUAGES
            }
            and requested_language.lower() != DEFAULT_LANGUAGE
        ):
            raise HTTPException(status_code=400, detail="Unsupported language")
        stored_language = normalized_language

    payload = {
        "account_id": effective_account_id,
        "name": name,
        "tone": requested_tone,
        "language": stored_language,
        "body": body,
    }

    try:
        result = await asyncio.to_thread(
            lambda: store.client.table("email_templates")
            .insert(payload)
            .execute()
        )
        rows = result.data or []
        if rows:
            return rows[0]
        return payload
    except Exception as e:
        logger.error(f"[TEMPLATES] Create failed for {effective_account_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create template")


@api_router.delete("/templates/{template_id}")
async def delete_template(template_id: str, account_id: str = Query(...)):
    """
    Delete a template for one account only.
    """
    store = safe_get_store()
    if not store:
        raise HTTPException(status_code=503, detail="Storage unavailable")

    effective_account_id = resolve_account_id(None, account_id)

    try:
        result = await asyncio.to_thread(
            lambda: store.client.table("email_templates")
            .delete()
            .eq("id", template_id)
            .eq("account_id", effective_account_id)
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Template not found")
        return {"status": "deleted", "id": template_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TEMPLATES] Delete failed for {effective_account_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete template")


@api_router.get("/preferences")
async def get_preferences(account_id: str = Query(...)):
    """
    Read per-account AI language preference.

    Behavior:
    - missing row -> English
    - null/invalid value -> English
    - lookup failure -> English
    """
    ai_language = "en"

    try:
        store = _get_preferences_store()
        response = (
            store.client.table("user_preferences")
            .select("ai_language")
            .eq("account_id", account_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if rows:
            ai_language = normalize_language(rows[0].get("ai_language"))
    except Exception as e:
        logger.warning(
            f"[PREFERENCES] Read failed for {account_id} "
            f"(type={type(e).__name__}) - defaulting to English"
        )

    return {
        "account_id": account_id,
        "ai_language": ai_language,
    }


@api_router.post("/preferences")
async def update_preferences(request: PreferencesUpdateRequest):
    """
    Upsert per-account AI language preference.

    Accepted values (DIM2 target set):
    - en, de, fr, es, pt-BR, ar, zh, ja, ko
    """
    requested = (request.ai_language or "").strip()
    normalized = normalize_language(requested)

    if normalized != requested:
        raise HTTPException(
            status_code=400,
            detail="ai_language must be one of: en, de, fr, es, pt-BR, ar, zh, ja, ko",
        )

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        store = _get_preferences_store()
        store.client.table("user_preferences").upsert(
            {
                "account_id": request.account_id,
                "ai_language": normalized,
                "updated_at": now_iso,
            },
            on_conflict="account_id",
        ).execute()

        return {
            "account_id": request.account_id,
            "ai_language": normalized,
        }
    except Exception as e:
        logger.error(
            f"[PREFERENCES] Write failed for {request.account_id} "
            f"(type={type(e).__name__}): {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to persist preferences",
        )


@api_router.get("/preferences/profile")
async def get_preferences_profile(account_id: str = Query(...)):
    """
    Read per-account AI priority profile.

    Behavior:
    - missing row -> {ai_priority_profile: null}
    - field null -> null
    - lookup failure -> HTTP 500
    """
    try:
        store = _get_preferences_store()
        response = (
            store.client.table("user_preferences")
            .select("ai_priority_profile")
            .eq("account_id", account_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        profile = rows[0].get("ai_priority_profile") if rows else None
    except Exception as e:
        logger.error(
            f"[PREFERENCES/PROFILE] Read failed for {account_id} "
            f"(type={type(e).__name__}): {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to read priority profile",
        )

    return {
        "account_id": account_id,
        "ai_priority_profile": profile,
    }


@api_router.put("/preferences/profile")
async def update_preferences_profile(request: PreferencesProfileUpdateRequest):
    """
    Write per-account AI priority profile.

    Uses read-then-update/insert to ensure ai_language and
    has_completed_onboarding are never silently clobbered.
    """
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        store = _get_preferences_store()
        existing = (
            store.client.table("user_preferences")
            .select("account_id")
            .eq("account_id", request.account_id)
            .limit(1)
            .execute()
        )
        row_exists = bool(existing.data)

        if row_exists:
            store.client.table("user_preferences").update(
                {
                    "ai_priority_profile": request.ai_priority_profile,
                    "updated_at": now_iso,
                }
            ).eq("account_id", request.account_id).execute()
        else:
            store.client.table("user_preferences").insert(
                {
                    "account_id": request.account_id,
                    "ai_priority_profile": request.ai_priority_profile,
                    "updated_at": now_iso,
                }
            ).execute()

        return {
            "account_id": request.account_id,
            "ai_priority_profile": request.ai_priority_profile,
        }
    except Exception as e:
        logger.error(
            f"[PREFERENCES/PROFILE] Write failed for {request.account_id} "
            f"(type={type(e).__name__}): {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to persist priority profile",
        )


@api_router.post("/translate")
async def translate_email_body(request: TranslateEmailRequest):
    """
    Translate an email body into the active account's preferred AI language.

    Contract:
      input  -> {"body": string, "target_language": "en|fr|ar"}
      output -> {"translated_body": string}

    Constraints:
      - body only; never headers
      - no persistence
      - authenticated route
    """
    body = (request.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Email body is required")

    requested_language = (request.target_language or "").strip().lower()
    normalized_language = normalize_translation_language(requested_language)
    if normalized_language != requested_language or normalized_language not in TRANSLATION_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="target_language must be one of: en, fr, ar",
        )

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Translation service unavailable")

    engine = MistralEngine(api_key=api_key)
    estimated_output_tokens = max(512, min(4096, engine.count_tokens(body) + 256))

    try:
        translated_body = await engine.generate_text_async(
            prompt=(
                f"Target language: {normalized_language}\n\n"
                f"Email body:\n{body}"
            ),
            max_tokens=estimated_output_tokens,
            temperature=0.2,
            system_prompt=_build_translation_system_prompt(normalized_language),
        )
    except ValueError:
        raise HTTPException(status_code=503, detail="Translation service unavailable")
    except TimeoutError:
        logger.warning(
            "[TRANSLATE] Timed out for language=%s body_chars=%s",
            normalized_language,
            len(body),
        )
        raise HTTPException(status_code=502, detail="Translation timed out")
    except Exception as e:
        logger.error(
            "[TRANSLATE] Failed (language=%s, type=%s)",
            normalized_language,
            type(e).__name__,
        )
        raise HTTPException(status_code=502, detail="Translation failed")

    translated_body = (translated_body or "").strip()
    if not translated_body:
        raise HTTPException(status_code=502, detail="Translation returned empty content")

    return {"translated_body": translated_body}


@api_router.post("/emails/{gmail_message_id}/translate-render")
async def translate_render_email(gmail_message_id: str, request: TranslateRenderRequest):
    """
    Message-bound translation endpoint returning an explicit translated render contract.

    Attempts structure-preserving HTML translation first (translation_mode="structured_html",
    translation_fidelity="preserved"). Falls back cleanly to plain-text translation
    (translation_mode="text_fallback", translation_fidelity="simplified") when HTML is absent
    or any step in the structured path fails.

    Contract:
      input  -> {"target_language": "en|fr|ar"}
      output -> TranslateRenderResponse
    """
    record = await asyncio.to_thread(_lookup_email_record_by_message_id, gmail_message_id)
    if not record:
        raise HTTPException(status_code=404, detail="Email not found")

    account_id = record.get("account_id")
    if not account_id:
        raise HTTPException(status_code=404, detail="Account not found for email")

    requested_language = (request.target_language or "").strip().lower()
    normalized_language = normalize_translation_language(requested_language)
    if normalized_language != requested_language or normalized_language not in TRANSLATION_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="target_language must be one of: en, fr, ar",
        )

    rendered_payload = await asyncio.to_thread(
        _build_rendered_email_payload,
        account_id,
        gmail_message_id,
        record.get("body") or "",
    )

    body_text = (rendered_payload.get("body_text") or record.get("body") or "").strip()
    if not body_text:
        raise HTTPException(status_code=400, detail="Email body is required for translation")

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Translation service unavailable")

    engine = MistralEngine(api_key=api_key)

    # Signal interactive-priority to governor so background AI worker defers
    # while this user-triggered translation is in-flight.
    _governor = _get_mistral_governor()
    _governor.begin_interactive()
    try:
        return await _translate_render_email_body(
            gmail_message_id=gmail_message_id,
            normalized_language=normalized_language,
            body_text=body_text,
            rendered_payload=rendered_payload,
            engine=engine,
        )
    finally:
        _governor.end_interactive()


async def _translate_render_email_body(
    *,
    gmail_message_id: str,
    normalized_language: str,
    body_text: str,
    rendered_payload: dict,
    engine,
):
    """Inner implementation of translate_render_email, called under governor protection."""
    # --- Attempt structure-preserving HTML translation ---
    translated_body_html: Optional[str] = None
    translation_mode = "text_fallback"
    translation_fidelity = "simplified"
    translation_reason_code = "text_fallback_used"

    body_html = (rendered_payload.get("body_html") or "").strip()
    _payload_body_text = body_text  # original payload body_text before any substitution
    _placeholder_map: Dict[str, str] = {}
    _use_protected_source: bool = False
    if body_html:
        if _is_html_preflight_degraded(body_html):
            # HTML is clearly too large/rich for reliable structured translation.
            # Skip the expensive JSON path entirely and go straight to text fallback.
            logger.info(
                "[TRANSLATE-RENDER] structured_preflight_degraded html_chars=%d "
                "imgs=%d hrefs=%d tables=%d -> routing directly to text fallback",
                len(body_html),
                body_html.lower().count("<img"),
                body_html.lower().count("href="),
                body_html.lower().count("<table"),
            )
            translation_reason_code = "structured_preflight_degraded"
            _protected_source, _placeholder_map = _derive_protected_fallback_source(body_html)
            # Apply block-scored canonicalization + token budget before source selection:
            # removes chrome blocks and caps translation input size to reduce chunk pressure.
            _normalized_body_text = _budget_rich_body_for_translation(body_text, engine)
            _prefer_derived, _src_reason = _select_canonical_translation_source(
                _normalized_body_text, _protected_source
            )
            if _prefer_derived:
                body_text = _protected_source
                _use_protected_source = True
            else:
                # Budgeted canonical body wins: use it as the translation input.
                body_text = _normalized_body_text
                _simplified_assist = _derive_simplified_fallback_source(body_html)
                body_text = _enrich_body_text_with_assists(body_text, _simplified_assist)
        else:
            try:
                translated_body_html, html_reason_code = await _attempt_structured_html_translation(
                    body_html, normalized_language, engine
                )
            except Exception as exc:
                logger.warning(
                    "[TRANSLATE-RENDER] Structured HTML attempt raised %s -> falling back to text mode",
                    type(exc).__name__,
                )
                translated_body_html = None
                html_reason_code = "structured_exception"

            if translated_body_html is not None:
                translation_mode = "structured_html"
                translation_fidelity = "preserved"
                translation_reason_code = "structured_success"
            else:
                translation_reason_code = html_reason_code
    else:
        translation_reason_code = "html_missing"

    # --- Text translation: primary when no HTML, explicit fallback otherwise ---
    translated_body_text: str

    if translation_mode == "text_fallback":
        _translation_system_prompt = _build_translation_system_prompt(
            normalized_language,
            protected_tokens=list(_placeholder_map.keys()) if _use_protected_source else None,
        )
        try:
            if _should_chunk_fallback_translation(body_text, engine):
                _chunks = _split_text_into_translation_chunks(body_text, engine)
                logger.info(
                    "[TRANSLATE-RENDER] chunked_fallback chunks=%d body_chars=%d language=%s",
                    len(_chunks),
                    len(body_text),
                    normalized_language,
                )
                translated_body_text = await _translate_text_chunks_async(
                    _chunks, normalized_language, engine, _translation_system_prompt,
                )
            else:
                estimated_output_tokens = max(512, min(4096, engine.count_tokens(body_text) + 256))
                translated_body_text = await engine.generate_text_async(
                    prompt=(
                        f"Target language: {normalized_language}\n\n"
                        f"Email body:\n{body_text}"
                    ),
                    max_tokens=estimated_output_tokens,
                    temperature=0.2,
                    system_prompt=_translation_system_prompt,
                )
        except ValueError:
            raise HTTPException(status_code=503, detail="Translation service unavailable")
        except TimeoutError:
            translation_reason_code = "text_translation_timeout"
            logger.warning(
                "[TRANSLATE-RENDER] %s language=%s body_chars=%s",
                translation_reason_code,
                normalized_language,
                len(body_text),
            )
            raise HTTPException(status_code=502, detail="Translation timed out")
        except Exception as e:
            translation_reason_code = "text_translation_failed"
            logger.error(
                "[TRANSLATE-RENDER] %s language=%s type=%s",
                translation_reason_code,
                normalized_language,
                type(e).__name__,
            )
            raise HTTPException(status_code=502, detail="Translation failed")

        translated_body_text = (translated_body_text or "").strip()
        if _use_protected_source and _placeholder_map:
            _missing_tokens = [t for t in _placeholder_map if t not in translated_body_text]
            if not _missing_tokens:
                translated_body_text = _restore_protected_tokens(translated_body_text, _placeholder_map)
            else:
                # One or more [[PROT_N]] tokens were dropped or mangled by the model.
                # Silently returning partial content would lose protected values (amounts,
                # reference numbers, brand names). Retry once with the simplified unwrap
                # source so the model sees protected content verbatim — no placeholder risk.
                logger.warning(
                    "[TRANSLATE-RENDER] protected_token_loss tokens_missing=%d "
                    "-> retrying without placeholder mode",
                    len(_missing_tokens),
                )
                _retry_source = _derive_simplified_fallback_source(body_html) or _payload_body_text
                _retry_sys = _build_translation_system_prompt(normalized_language)
                try:
                    if _should_chunk_fallback_translation(_retry_source, engine):
                        _retry_chunks = _split_text_into_translation_chunks(_retry_source, engine)
                        translated_body_text = await _translate_text_chunks_async(
                            _retry_chunks, normalized_language, engine, _retry_sys,
                        )
                    else:
                        translated_body_text = await engine.generate_text_async(
                            prompt=(
                                f"Target language: {normalized_language}\n\n"
                                f"Email body:\n{_retry_source}"
                            ),
                            max_tokens=max(512, min(4096, engine.count_tokens(_retry_source) + 256)),
                            temperature=0.2,
                            system_prompt=_retry_sys,
                        )
                except ValueError:
                    raise HTTPException(status_code=503, detail="Translation service unavailable")
                except TimeoutError:
                    translation_reason_code = "text_translation_timeout"
                    logger.warning(
                        "[TRANSLATE-RENDER] retry_timeout language=%s body_chars=%s",
                        normalized_language,
                        len(_retry_source),
                    )
                    raise HTTPException(status_code=502, detail="Translation timed out")
                except Exception as _retry_exc:
                    translation_reason_code = "text_translation_failed"
                    logger.error(
                        "[TRANSLATE-RENDER] retry_failed language=%s type=%s",
                        normalized_language,
                        type(_retry_exc).__name__,
                    )
                    raise HTTPException(status_code=502, detail="Translation failed")
                translated_body_text = (translated_body_text or "").strip()
        if translation_reason_code == "structured_preflight_degraded":
            translated_body_text = _trim_footer_tail(translated_body_text)
            translated_body_text = _dedup_repeated_blocks(translated_body_text)
        if not translated_body_text:
            raise HTTPException(status_code=502, detail="Translation returned empty content")
    else:
        # Derive plain-text from translated HTML for the text field.
        # _derive_plain_text_from_html removes hidden elements and collapses
        # blank lines before returning — see its docstring for details.
        assert translated_body_html is not None
        translated_body_text = _derive_plain_text_from_html(translated_body_html)

    return {
        "gmail_message_id": gmail_message_id,
        "target_language": normalized_language,
        "translation_mode": translation_mode,
        "translation_fidelity": translation_fidelity,
        "translation_reason_code": translation_reason_code,
        "translated_body_html": translated_body_html,
        "translated_body_text": translated_body_text,
        "attachments": rendered_payload.get("attachments") or [],
        "linked_files": rendered_payload.get("linked_files") or [],
    }


@api_router.post("/emails/{gmail_message_id}/summarize")
async def summarize_email_by_id(
    gmail_message_id: str,
    account_id: str = Query("default"),
    preferred_language: Optional[str] = Query(None),
    ai_language: Optional[str] = Query(None),
):
    """
    Enqueue AI summarization job for specific email.

    User-triggered action when clicking "Summarize Email" button.

    Args:
        gmail_message_id: Gmail's stable message ID
        account_id: Account identifier (from query param)
        preferred_language: Desired output language (takes priority over ai_language)
        ai_language: Alias for preferred_language

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

    # Normalize the requested language; fall back to "en" if absent/invalid
    raw_lang = preferred_language or ai_language
    effective_language = normalize_language(raw_lang) if raw_lang else None

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

        # Enqueue AI summarization job with language hint
        job_id = await asyncio.to_thread(
            store.enqueue_ai_job,
            account_id=effective_account_id,
            gmail_message_id=gmail_message_id,
            job_type="email_summarize_v1",
            ai_language=effective_language,
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

