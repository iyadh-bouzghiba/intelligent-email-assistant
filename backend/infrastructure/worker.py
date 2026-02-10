import os
import time
import asyncio
from datetime import datetime
from backend.core import EmailAssistant
from backend.infrastructure.control_plane import ControlPlane

# Socket.IO for realtime notifications
try:
    from backend.api.service import sio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    print("[WARN] [WORKER] Socket.IO not available - realtime updates disabled")

# Shared operational heartbeat - accessible by health check server
WORKER_HEARTBEAT = {"last_cycle": None}


def run_worker_loop():
    """
    Core background processing loop. 
    Hardened for Render Free Tier: Never exits, logs cycles, handles backoff.
    Enterprise Ready: Obeys ControlPlane policies and audit trails.
    """
    print("[WORKER] Background worker loop initialized")
    assistant = EmailAssistant()
    control = ControlPlane()

    # PHASE 4: DEPLOYMENT SAFETY CONTRACT
    control.verify_schema()  # sets ControlPlane.schema_state
    if ControlPlane.schema_state != "ok":
        print(f"[WARN] [WORKER] Schema state: {ControlPlane.schema_state}. Writes disabled. Worker idle.")
        while True:
            WORKER_HEARTBEAT["last_cycle"] = time.time()
            time.sleep(60)

    while True:
        try:
            # Update heartbeat before blocking operations
            WORKER_HEARTBEAT["last_cycle"] = time.time()
            
            # PHASE 1: CONTROL PLANE ENFORCEMENT
            if not control.is_worker_enabled():
                print("[WORKER] Ingestion suspended by ControlPlane policy.")
                time.sleep(60)
                continue

            print(f"[WORKER] Cycle started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            control.log_audit("cycle_start", "gmail_ingest")
            
            # Fetch emails via the domain assistant
            emails = assistant.process_emails()

            # Detect auth error and enter quiet mode
            if isinstance(emails, dict) and emails.get("__auth_error__") == "invalid_grant":
                print("[WARN] [WORKER] Gmail auth invalid. Re-auth required at /auth/google")
                print("[WORKER] Entering quiet mode: 10 minute backoff")
                time.sleep(600)  # 10 minutes
                continue

            if emails:
                # Enforce cycle quota
                max_emails = control.max_emails_per_cycle()
                if len(emails) > max_emails:
                    print(f"[WARN] [WORKER] Truncating cycle from {len(emails)} to {max_emails} (Policy)")
                    emails = emails[:max_emails]

                print(f"[WORKER] Gmail fetch success: {len(emails)} emails")
            else:
                print("[WORKER] Gmail fetch: No new emails found")

            # PHASE 3: REAL-TIME BACKPRESSURE (Batch Commits)
            batch_size = 25
            for i in range(0, len(emails), batch_size):
                batch = emails[i : i + batch_size]
                
                for email in batch:
                    # INGEST-FIX-02: Robust gmail_id extraction with fallback chain
                    m_id = email.get('message_id') or email.get('id')

                    # CRITICAL: Never ingest emails without valid Gmail ID (breaks dedup contract)
                    if not m_id:
                        print(f"[WORKER] SKIP: Missing gmail_id for subject: {email.get('subject', 'No Subject')}")
                        continue

                    # Deduplication key originates from source-of-truth date
                    date_val = email.get('date') or datetime.utcnow().isoformat()

                    print(f"[WORKER] Ingesting: {email.get('subject', 'No Subject')} (gmail_id={m_id})")

                    control.store.save_email(
                        subject=email.get('subject', 'No Subject'),
                        sender=email.get('sender', 'Unknown'),
                        date=date_val,
                        body=email.get('body', ''),  # INGEST-FIX-02: Use Gmail body, not AI summary
                        message_id=m_id,
                        tenant_id="primary"
                    )
                
                # Sleep between batches for backpressure
                if i + batch_size < len(emails):
                    print(f"[WORKER] Batch commit complete. Cooling for 500ms...")
                    time.sleep(0.5)
            
            if emails:
                control.log_audit("ingestion_complete", "supabase", {"count": len(emails)})
                print(f"[WORKER] Supabase write complete: {len(emails)} emails ingested")

                # Emit realtime notification to connected clients
                if SOCKETIO_AVAILABLE:
                    try:
                        # Use asyncio.run to properly await the async emit in sync context
                        asyncio.run(sio.emit("emails_updated", {
                            "count": len(emails),
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                        print(f"[WORKER] Socket.IO event emitted: emails_updated (count={len(emails)})")
                    except Exception as e:
                        print(f"[WARN] [WORKER] Socket.IO emission failed: {e}")

            print("[WORKER] Cycle complete — sleeping 60s")
            time.sleep(60)

        except Exception as e:
            print(f"[WORKER] ERROR: {e}")
            print("[WORKER] Backing off 120s")
            time.sleep(120)

if __name__ == "__main__":
    # Local Windows / Manual test support
    WORKER_MODE = os.getenv("WORKER_MODE", "false").lower() == "true"
    if WORKER_MODE:
        run_worker_loop()
    else:
        print("Worker mode disabled — safe exit")
