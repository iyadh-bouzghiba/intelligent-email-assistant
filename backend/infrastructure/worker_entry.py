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
    FAIL-FAST STARTUP VALIDATION - Deployment Safety Contract

    This function implements a ZERO-TOLERANCE validation policy that:
    - Fails immediately if 'src' appears anywhere in module resolution paths
    - Verifies backend package is importable (prevents ModuleNotFoundError)
    - Confirms execution mode is package-based (-m flag)
    - Validates Python version compatibility
    - Checks package context integrity

    Exits with status 1 if ANY validation fails.
    Prevents silent failures by enforcing strict architectural contracts.
    """
    import sys
    print("[BOOT] [VALIDATION] Starting FAIL-FAST startup checks...")
    errors = []
    warnings = []

    # ========== CRITICAL: 'src' PATH CONTAMINATION CHECK ==========
    # If 'src' appears in sys.path, we risk importing from deleted/old modules
    # This is the #1 cause of ModuleNotFoundError in this project
    print("[BOOT] [VALIDATION] Checking for 'src' path contamination...")
    for path in sys.path:
        if 'src' in path and 'site-packages' not in path:
            errors.append(f"FORBIDDEN PATH DETECTED: sys.path contains 'src' reference: {path}")
            print(f"[FAIL] [VALIDATION] Forbidden 'src' in sys.path: {path}")

    if not errors:
        print("[OK] [VALIDATION] No 'src' contamination in sys.path")

    # ========== PACKAGE CONTEXT VERIFICATION ==========
    # Ensure we're running as a package module (via -m flag)
    print(f"[BOOT] [VALIDATION] Package context: __package__={__package__}")
    if not __package__:
        errors.append("Not executed as package module (missing -m flag)")
        print("[FAIL] [VALIDATION] Not executed via -m flag")
        print(f"[FAIL] [VALIDATION] Current __package__: {__package__}")
        print(f"[FAIL] [VALIDATION] Current __name__: {__name__}")
    else:
        print(f"[OK] [VALIDATION] Package execution confirmed: {__package__}")

    # ========== BACKEND PACKAGE IMPORTABILITY ==========
    # Verify 'backend' package is on sys.path and importable
    print("[BOOT] [VALIDATION] Testing backend package import...")
    try:
        import backend
        backend_path = backend.__file__ if hasattr(backend, '__file__') else backend.__path__
        print(f"[OK] [VALIDATION] backend package found at: {backend_path}")
    except ImportError as e:
        errors.append(f"backend package not importable: {e}")
        print(f"[FAIL] [VALIDATION] Cannot import backend: {e}")

    # ========== CRITICAL MODULE IMPORTS ==========
    # Test imports of critical application modules
    print("[BOOT] [VALIDATION] Testing critical module imports...")
    critical_modules = [
        ("backend.api.service", "Main API service"),
        ("backend.infrastructure.control_plane", "Control plane"),
        ("backend.core", "Core logic"),
        ("backend.config", "Configuration"),
    ]

    for module_name, description in critical_modules:
        try:
            __import__(module_name)
            print(f"[OK] [VALIDATION] {module_name} ({description})")
        except ImportError as e:
            errors.append(f"{description} import failed: {e}")
            print(f"[FAIL] [VALIDATION] Cannot import {module_name}: {e}")

    # ========== PYTHON VERSION CHECK ==========
    print(f"[BOOT] [VALIDATION] Python version: {sys.version}")
    if sys.version_info < (3, 9):
        errors.append(f"Python 3.9+ required, found {sys.version_info.major}.{sys.version_info.minor}")
        print(f"[FAIL] [VALIDATION] Unsupported Python version")
    else:
        print(f"[OK] [VALIDATION] Python {sys.version_info.major}.{sys.version_info.minor} supported")

    # ========== ENVIRONMENT DIAGNOSTICS ==========
    print("[BOOT] [VALIDATION] Environment diagnostics:")
    print(f"[INFO] Working directory: {os.getcwd()}")
    print(f"[INFO] sys.path entries: {len(sys.path)}")
    for idx, path in enumerate(sys.path[:5]):
        print(f"[INFO]   [{idx}] {path}")

    # ========== FAIL-FAST EXIT ==========
    if errors:
        print("\n" + "="*80)
        print("🚨 [CRITICAL] STARTUP VALIDATION FAILED - CANNOT PROCEED 🚨")
        print("="*80)
        print("\nCRITICAL ERRORS:")
        for idx, error in enumerate(errors, 1):
            print(f"  {idx}. {error}")
        print("\n" + "="*80)
        print("DEPLOYMENT CONTRACT VIOLATION DETECTED")
        print("="*80)
        print("\n💡 RESOLUTION STEPS:")
        print("  1. Verify Dockerfile uses: CMD [\"python\", \"-m\", \"backend.infrastructure.worker_entry\"]")
        print("  2. Ensure backend/ contains __init__.py")
        print("  3. Confirm no 'src/' directory exists in backend/")
        print("  4. Check that 'pip install -e .' was run (if using editable install)")
        print("\n🔧 CORRECT EXECUTION:")
        print("  python -m backend.infrastructure.worker_entry")
        print("\n" + "="*80)
        sys.exit(1)

    if warnings:
        print("\n" + "⚠"*40)
        print("WARNINGS (non-fatal):")
        for warning in warnings:
            print(f"  - {warning}")
        print("⚠"*40 + "\n")

    print("="*80)
    print("✅ [VALIDATION] ALL STARTUP CHECKS PASSED - SYSTEM READY")
    print("="*80)
    print(f"[OK] Package Context: {__package__}")
    print(f"[OK] Execution Mode: Module (-m flag)")
    print(f"[OK] Import Resolution: backend.* imports working")
    print(f"[OK] Path Integrity: No 'src' contamination")
    print("="*80)


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
            print(f"[WARN] [WORKER] Loop crashed, restarting in 30s: {e}")
            time.sleep(30)


if __name__ == "__main__":
    # Render provides PORT; default 8888 for local dev
    port = int(os.getenv("PORT", "8888"))

    if WORKER_MODE:
        # HYBRID MODE: background worker + full API in one process.
        # Render free tier allows only one web service; this pattern keeps
        # both the email-sync worker loop and all API/OAuth/WebSocket routes
        # alive on a single dyno.
        print("[START] [BOOT] Running in Hybrid Mode (API + Background Worker)")
        t = threading.Thread(target=start_worker, daemon=True)
        t.start()
    else:
        print("[START] [BOOT] Running in API-only Mode")

    # Both modes serve the main API (sio_app).
    # /health and /healthz are on sio_app; Render health check hits /healthz.
    from backend.api.service import sio_app
    print(f"[NET] [BOOT] API server listening on 0.0.0.0:{port}")
    uvicorn.run(sio_app, host="0.0.0.0", port=port, log_level="info", timeout_keep_alive=120)
