"""
AI Email Summarization Worker Entrypoint

Standalone worker daemon for email summarization jobs.
Runs only if AI_SUMM_ENABLED=true.

CRITICAL: This is a worker-only process. Do NOT invoke from API handlers.
"""

import logging
import os
import time
import socket
from backend.infrastructure.ai_summarizer_worker import AISummarizerWorker
from backend.infrastructure.supabase_store import SupabaseStore
from backend.engine.nlp_engine import MistralEngine

logger = logging.getLogger(__name__)

# Shared operational heartbeat for the AI summarizer worker.
# Readable by the API healthz endpoint when both run in the same process.
AI_WORKER_HEARTBEAT: dict = {
    "enabled": None,
    "status": "initializing",
    "worker_id": None,
    "started_at": None,
    "last_loop_at": None,
    "last_claimed_at": None,
    "last_processed_at": None,
    "last_idle_at": None,
    "last_batch_size": None,
    "last_error_at": None,
    "last_error_type": None,
    "last_error_message": None,
}

# Environment configuration
AI_SUMM_ENABLED = os.getenv("AI_SUMM_ENABLED", "false").lower() == "true"
AI_JOBS_BATCH = int(os.getenv("AI_JOBS_BATCH", "5"))
AI_IDLE_SLEEP = int(os.getenv("AI_IDLE_SLEEP", "5"))
AI_WORKER_ID = os.getenv("AI_WORKER_ID")


def require_env(vars: list[str]) -> bool:
    """
    Check required environment variables.

    Returns True if all present, False if any missing.
    Logs missing vars (names only, not values).
    """
    missing = [var for var in vars if not os.getenv(var)]

    if missing:
        logger.error(f"[AI-WORKER] Missing required env vars: {', '.join(missing)}")
        return False

    return True


def get_stable_worker_id() -> str:
    """Generate stable worker ID from hostname + PID."""
    if AI_WORKER_ID:
        return AI_WORKER_ID

    hostname = socket.gethostname()
    pid = os.getpid()
    return f"{hostname}-{pid}"


def main():
    """Main worker loop."""
    # Configure logging (critical when called as imported function, not __main__)
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",  # Simple format to match worker_entry.py print() style
        force=True  # Override any existing config
    )

    if not AI_SUMM_ENABLED:
        logger.info("[AI-WORKER] AI_SUMM_ENABLED=false. Worker disabled. Exiting.")
        AI_WORKER_HEARTBEAT.update({"enabled": False, "status": "disabled"})
        return

    worker_id = get_stable_worker_id()
    logger.info(f"[AI-WORKER] Starting worker: {worker_id}")
    logger.info(f"[AI-WORKER] Config: BATCH={AI_JOBS_BATCH}, IDLE_SLEEP={AI_IDLE_SLEEP}s")
    AI_WORKER_HEARTBEAT.update({
        "enabled": True,
        "status": "starting",
        "worker_id": worker_id,
        "started_at": time.time(),
    })

    # Check required environment variables
    if not require_env(["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "MISTRAL_API_KEY"]):
        logger.error("[AI-WORKER] Cannot start worker without required env vars. Exiting.")
        AI_WORKER_HEARTBEAT.update({
            "status": "init_failed",
            "last_error_at": time.time(),
            "last_error_type": "MissingEnvVars",
            "last_error_message": "Missing one or more required env vars",
        })
        return

    # Initialize dependencies
    try:
        store = SupabaseStore()
        mistral_engine = MistralEngine()
        worker = AISummarizerWorker(store, mistral_engine)
    except Exception as e:
        err_type = type(e).__name__
        logger.error(f"[AI-WORKER] Initialization failed (type={err_type})")
        AI_WORKER_HEARTBEAT.update({
            "status": "init_failed",
            "last_error_at": time.time(),
            "last_error_type": err_type,
            "last_error_message": str(e)[:200],
        })
        return

    # Main processing loop
    logger.info("[AI-WORKER] Entering main loop")
    AI_WORKER_HEARTBEAT["status"] = "running"

    try:
        while True:
            try:
                AI_WORKER_HEARTBEAT["last_loop_at"] = time.time()

                # Claim and process batch
                processed = worker.process_batch(AI_JOBS_BATCH, worker_id)

                AI_WORKER_HEARTBEAT["last_batch_size"] = processed

                if processed == 0:
                    # No jobs available - idle sleep
                    logger.info(f"[AI-WORKER] No jobs claimed. Sleeping {AI_IDLE_SLEEP}s")
                    AI_WORKER_HEARTBEAT.update({
                        "status": "idle",
                        "last_idle_at": time.time(),
                    })
                    time.sleep(AI_IDLE_SLEEP)
                else:
                    # Jobs processed - continue immediately
                    logger.info(f"[AI-WORKER] Processed {processed} jobs. Checking for more...")
                    _now = time.time()
                    AI_WORKER_HEARTBEAT.update({
                        "status": "running",
                        "last_claimed_at": _now,
                        "last_processed_at": _now,
                    })

            except KeyboardInterrupt:
                logger.info("[AI-WORKER] Received shutdown signal. Exiting gracefully.")
                break
            except Exception as e:
                err_type = type(e).__name__
                logger.error(f"[AI-WORKER] Batch processing error (type={err_type})")
                AI_WORKER_HEARTBEAT.update({
                    "status": "error",
                    "last_error_at": time.time(),
                    "last_error_type": err_type,
                    "last_error_message": str(e)[:200],
                })
                # Sleep on error to prevent tight error loops
                time.sleep(AI_IDLE_SLEEP)

    finally:
        logger.info("[AI-WORKER] Worker shutdown complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    main()
