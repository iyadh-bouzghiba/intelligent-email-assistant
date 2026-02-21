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
    if not AI_SUMM_ENABLED:
        logger.info("[AI-WORKER] AI_SUMM_ENABLED=false. Worker disabled. Exiting.")
        return

    worker_id = get_stable_worker_id()
    logger.info(f"[AI-WORKER] Starting worker: {worker_id}")
    logger.info(f"[AI-WORKER] Config: BATCH={AI_JOBS_BATCH}, IDLE_SLEEP={AI_IDLE_SLEEP}s")

    # Check required environment variables
    if not require_env(["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "MISTRAL_API_KEY"]):
        logger.error("[AI-WORKER] Cannot start worker without required env vars. Exiting.")
        return

    # Initialize dependencies
    try:
        store = SupabaseStore()
        mistral_engine = MistralEngine()
        worker = AISummarizerWorker(store, mistral_engine)
    except Exception as e:
        err_type = type(e).__name__
        logger.error(f"[AI-WORKER] Initialization failed (type={err_type})")
        return

    # Main processing loop
    logger.info("[AI-WORKER] Entering main loop")

    try:
        while True:
            try:
                # Claim and process batch
                processed = worker.process_batch(AI_JOBS_BATCH, worker_id)

                if processed == 0:
                    # No jobs available - idle sleep
                    logger.debug(f"[AI-WORKER] No jobs claimed. Sleeping {AI_IDLE_SLEEP}s")
                    time.sleep(AI_IDLE_SLEEP)
                else:
                    # Jobs processed - continue immediately
                    logger.info(f"[AI-WORKER] Processed {processed} jobs. Checking for more...")

            except KeyboardInterrupt:
                logger.info("[AI-WORKER] Received shutdown signal. Exiting gracefully.")
                break
            except Exception as e:
                err_type = type(e).__name__
                logger.error(f"[AI-WORKER] Batch processing error (type={err_type})")
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
