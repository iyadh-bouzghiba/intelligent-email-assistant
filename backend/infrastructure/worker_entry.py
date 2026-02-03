"""
Intelligent Email Assistant - Worker Entry Point

This module serves as the application entry point, supporting two modes:
- WORKER_MODE=true: Background email processing with /healthz endpoint (port 8888)
- WORKER_MODE=false: Full API with OAuth and WebSocket support (port 8000)

Execution:
    cd intelligent-email-assistant
    python -m backend.infrastructure.worker_entry

Bootstrap:
    Python's module execution via -m automatically adds the project root to sys.path.
    No manual path manipulation needed.
"""
import os

# Minimal bootstrap: Ensure we're running as a module
if __name__ != "__main__" and not __package__:
    print("[WARN] [BOOT] Not executed as module. Import resolution may fail.")
    print("[TIP] Run via: python -m backend.infrastructure.worker_entry")

# WORKER_MODE controlled by .env file (don't hardcode here)
# os.environ["WORKER_MODE"] = "true"

import threading
from fastapi import FastAPI
import uvicorn

import time
# Absolute import from root
from backend.infrastructure.worker import run_worker_loop, WORKER_HEARTBEAT


def validate_startup():
    """
    Startup validation - Fail-fast on critical configuration errors.

    Validates:
    - Python package structure (imports resolve correctly)
    - Required environment variables exist
    - Critical modules are importable

    Exits with status 1 if any validation fails.
    """
    print("[BOOT] [VALIDATION] Starting startup checks...")
    errors = []

    # Check critical imports
    try:
        from backend.api import service
        from backend.infrastructure import control_plane
        from backend.core import EmailAssistant
        print("[OK] [VALIDATION] All critical modules importable")
    except ImportError as e:
        errors.append(f"Import validation failed: {e}")
        print(f"[FAIL] [VALIDATION] Import error: {e}")

    # Check Python version
    import sys
    if sys.version_info < (3, 9):
        errors.append(f"Python 3.9+ required, found {sys.version_info.major}.{sys.version_info.minor}")
        print(f"[FAIL] [VALIDATION] Unsupported Python version: {sys.version}")

    # Check package execution mode
    if not __package__:
        errors.append("Not executed as package module")
        print("[WARN] [VALIDATION] Not executed via -m flag (may cause import issues)")

    # Fail fast if errors found
    if errors:
        print("\n" + "="*70)
        print("[FAIL] [CRITICAL] Startup validation FAILED. Cannot proceed.")
        print("="*70)
        for error in errors:
            print(f"  - {error}")
        print("="*70)
        print("[TIP] Fix errors above and restart")
        print("[TIP] Run via: python -m backend.infrastructure.worker_entry")
        sys.exit(1)

    print("[OK] [VALIDATION] All startup checks passed")


# Run validation before proceeding
validate_startup()

WORKER_MODE = os.getenv("WORKER_MODE", "false").lower() == "true"

app = FastAPI(title="Email Assistant - Headless Worker")

@app.get("/healthz")
def healthz():
    """Truthful health contract: Returns status based on worker execution age"""
    last = WORKER_HEARTBEAT.get("last_cycle")
    age = time.time() - last if last else 999999
    
    # Render survival logic: worker-ok if loop is active within 180s
    status = "worker-ok" if age < 180 else "stalled"
    
    return {
        "status": status,
        "last_cycle_seconds_ago": int(age) if last else -1,
        "mode": "worker"
    }

def start_worker():
    print("[WORKER] Starting Email Assistant Worker Loop...")
    while True:
        try:
            run_worker_loop()
        except Exception as e:
            print(f"[WORKER] FATAL LOOP CRASH: {e}")
            print("[WORKER] Restarting loop in 30s")
            time.sleep(30)


if __name__ == "__main__":
    # Port 8888 for local development (Google OAuth configured)
    # Render will override with PORT env var (typically 10000)
    port = int(os.getenv("PORT", "8888"))
    
    if WORKER_MODE:
        print("[START] [BOOT] Running in FREE Render Web Worker Mode")

        # Start processing in a background daemon thread
        t = threading.Thread(target=start_worker, daemon=True)
        t.start()

        # Start FastAPI to satisfy Render's HTTP requirement + provide health telemetry
        print(f"[NET] [BOOT] Worker Health server listening on 0.0.0.0:{port}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", timeout_keep_alive=120)
    else:
        print("[START] [BOOT] Running in API Mode")
        from backend.api.service import sio_app
        print(f"[NET] [BOOT] API server listening on 0.0.0.0:{port}")
        uvicorn.run(sio_app, host="0.0.0.0", port=port, log_level="info", timeout_keep_alive=120)
