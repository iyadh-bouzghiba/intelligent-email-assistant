import os
import time
import asyncio
import json
import logging
from datetime import datetime
from backend.core import EmailAssistant
from backend.infrastructure.control_plane import ControlPlane

# Configure logger for worker process
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Socket.IO for realtime notifications
try:
    from backend.api.service import sio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    print("[WARN] [WORKER] Socket.IO not available - realtime updates disabled")

# Shared operational heartbeat - accessible by health check server
WORKER_HEARTBEAT = {"last_cycle": None}


def _load_token_data() -> dict:
    """Load OAuth token for cursor operations (Supabase first, file fallback in dev)."""
    try:
        from backend.auth.credential_store import CredentialStore
        from backend.data.store import PersistenceManager

        persistence = PersistenceManager()
        credential_store = CredentialStore(persistence)
        tokens = credential_store.load_credentials("default")
        if tokens:
            return tokens
    except Exception as e:
        print(f"[WARN] [WORKER] Failed to load credentials: {e}")

    # Dev fallback
    env = os.getenv("ENVIRONMENT", "production").lower()
    allow_file = os.getenv("ALLOW_FILE_CREDENTIALS", "false").lower() == "true"
    if env in ["local", "development"] or allow_file:
        path = os.getenv("GMAIL_CREDENTIALS_PATH", "")
        if path:
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def _extract_message_ids_from_history(history_records):
    """Extract unique Gmail message IDs from history API response."""
    message_ids = set()
    for record in history_records:
        # messagesAdded contains new messages
        if 'messagesAdded' in record:
            for msg_added in record['messagesAdded']:
                msg_id = msg_added.get('message', {}).get('id')
                if msg_id:
                    message_ids.add(msg_id)
    return list(message_ids)


def _fetch_and_transform_messages(gmail_client, message_ids, assistant):
    """
    Fetch messages by ID and transform to worker ingest format.
    Returns list of dicts with keys: message_id, subject, sender, date, body, summary.
    """
    from backend.services.gmail_engine import get_message_body
    from email.utils import parsedate_to_datetime

    results = []
    for msg_id in message_ids:
        try:
            msg = gmail_client.get_message(msg_id)
            label_ids = msg.get('labelIds', []) or []
            if "INBOX" not in label_ids:
                continue

            payload = msg.get('payload', {})
            headers = payload.get('headers', [])

            # Extract metadata
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "No Subject")
            sender_raw = next((h['value'] for h in headers if h['name'].lower() == 'from'), "Unknown")
            date_header = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)

            # Use internalDate as authoritative timestamp
            # CRITICAL FIX: Use timezone-aware datetime to prevent drift
            from datetime import timezone

            internal_date_ms = msg.get('internalDate')
            timestamp_source = "unknown"

            if internal_date_ms:
                # ✅ FIXED: Use timezone-aware conversion (not deprecated utcfromtimestamp)
                dt_utc = datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)
                date_iso = dt_utc.isoformat()
                timestamp_source = "internalDate"
                logger.info(f"[TIMESTAMP-FIX-WORKER] {subject[:30]}... | internalDate: {internal_date_ms}ms | UTC: {date_iso} | Source: {timestamp_source}")
            elif date_header:
                try:
                    parsed_dt = parsedate_to_datetime(date_header)
                    # Ensure timezone-aware
                    if parsed_dt.tzinfo is None:
                        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                    date_iso = parsed_dt.isoformat()
                    timestamp_source = "date_header"
                    logger.info(f"[TIMESTAMP-FIX-WORKER] {subject[:30]}... | Date header: {date_header} | UTC: {date_iso} | Source: {timestamp_source}")
                except Exception as e:
                    dt_utc = datetime.now(timezone.utc)
                    date_iso = dt_utc.isoformat()
                    timestamp_source = "fallback_now"
                    logger.warning(f"[TIMESTAMP-FIX-WORKER] {subject[:30]}... | Date parse failed: {e} | UTC: {date_iso} | Source: {timestamp_source}")
            else:
                dt_utc = datetime.now(timezone.utc)
                date_iso = dt_utc.isoformat()
                timestamp_source = "fallback_now"
                logger.warning(f"[TIMESTAMP-FIX-WORKER] {subject[:30]}... | No timestamp found | UTC: {date_iso} | Source: {timestamp_source}")

            # Extract body
            raw_body = get_message_body(payload)
            cleaned_body = raw_body.strip()

            # Generate summary
            email_dict = {
                "subject": subject,
                "sender": sender_raw,
                "date": date_iso,
                "body": cleaned_body
            }

            # WORKER-PERF-01: Do not block ingestion with summarization.
            # SUMM-RT-01 will handle summaries asynchronously post-ingest.
            summary = ""

            results.append({
                "message_id": msg['id'],
                "subject": subject,
                "sender": sender_raw,
                "date": date_iso,
                "body": cleaned_body,
                "summary": summary
            })
        except Exception as e:
            print(f"[WARN] [WORKER] Failed to fetch message {msg_id}: {e}")
            continue

    return results


def run_worker_loop():
    """
    Core background processing loop with Gmail History API cursor tracking.
    WORKER-PERF-01: Detects no-op cycles to eliminate redundant DB writes and Socket.IO emissions.
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

    # WORKER-PERF-01: Initialize cursor tracking
    tenant_id = "primary"
    account_id = "default"
    gmail_client = None

    # Try to create GmailClient for cursor operations
    token_data = _load_token_data()
    if token_data and 'token' in token_data:
        try:
            from backend.api.gmail_client import GmailClient
            # Transform token_data format to match GmailClient expectations
            client_token_data = {
                "access_token": token_data.get("token"),
                "refresh_token": token_data.get("refresh_token"),
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": token_data.get("client_id"),
                "client_secret": token_data.get("client_secret"),
                "scopes": token_data.get("scopes", [])
            }
            gmail_client = GmailClient(client_token_data)
            print("[OK] [WORKER] GmailClient initialized for cursor tracking")
        except Exception as e:
            print(f"[WARN] [WORKER] GmailClient init failed: {e}. Cursor tracking disabled.")

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

            # WORKER-PERF-01: Cursor-based delta ingestion
            last_cursor = None
            current_cursor = None
            changed_ids_count = 0
            fetched_emails_count = 0
            written_count = 0
            emitted = False
            emails = []

            if not gmail_client:
                # Fallback to full sync if GmailClient unavailable
                print("[WORKER] GmailClient unavailable. Using full sync mode.")
                emails = assistant.process_emails()
            else:
                try:
                    last_cursor = control.store.get_sync_state(tenant_id, account_id)
                    current_cursor = gmail_client.get_current_history_id()

                    if not current_cursor:
                        raise RuntimeError("Gmail profile returned NULL historyId - cannot continue")

                    print(f"[WORKER] Cursor state: last={last_cursor[:8] if last_cursor else 'NULL'}..., current={current_cursor[:8]}...")

                    # Case 1: First run (no cursor saved)
                    if not last_cursor:
                        print("[WORKER] First run detected (NULL cursor). Running bounded full sync to seed data.")
                        emails = assistant.process_emails()

                    # Case 2: NO-OP (cursor unchanged)
                    elif last_cursor == current_cursor:
                        print(f"[WORKER] NO-OP: historyId unchanged ({current_cursor[:8]}...). Skip fetch/ingest.")
                        print(f"[WORKER] Counters: changed_ids_count=0, fetched_emails_count=0, written_count=0, emitted=false")
                        print("[WORKER] Cycle complete (NO-OP) - sleeping 60s")
                        time.sleep(60)
                        continue

                    # Case 3: Delta sync (cursor changed)
                    else:
                        print(f"[WORKER] Delta sync: historyId changed from {last_cursor[:8]}... to {current_cursor[:8]}...")
                        history_records = gmail_client.list_history(start_history_id=last_cursor, history_types=["messageAdded"])

                        # Handle 404 "historyId too old" (list_history returns None)
                        if history_records is None:
                            print("[WARN] [WORKER] History API indicates cursor too old (404). Fallback to bounded full sync.")
                            emails = assistant.process_emails()
                        else:
                            # Extract changed message IDs (may be empty list - valid case)
                            changed_ids = _extract_message_ids_from_history(history_records)
                            changed_ids_count = len(changed_ids)
                            print(f"[WORKER] History API returned {changed_ids_count} changed message(s).")

                            if changed_ids_count > 0:
                                # Fetch ONLY changed messages
                                emails = _fetch_and_transform_messages(gmail_client, changed_ids, assistant)
                                fetched_emails_count = len(emails)
                                print(f"[WORKER] Fetched {fetched_emails_count} message(s) via delta sync.")
                            else:
                                # Valid: cursor changed but no messageAdded entries in this delta
                                emails = []
                                print("[WORKER] No messageAdded events in history delta.")

                except Exception as e:
                    print(f"[WARN] [WORKER] Delta sync failed: {e}. Fallback to full sync.")
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
            if emails:
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
                            tenant_id="primary",
                            account_id=account_id
                        )
                        written_count += 1

                        # CRITICAL: Enqueue AI summarization job for recent emails only (30-email limit)
                        if written_count <= 30:
                            control.store.enqueue_ai_job(
                                account_id=account_id,
                                gmail_message_id=m_id,
                                job_type="email_summarize_v1"
                            )

                    # Sleep between batches for backpressure
                    if i + batch_size < len(emails):
                        print(f"[WORKER] Batch commit complete. Cooling for 500ms...")
                        time.sleep(0.5)

                control.log_audit("ingestion_complete", "supabase", {"count": written_count})
                print(f"[WORKER] Supabase write complete: {written_count} email(s) ingested")

                # Emit realtime notification ONLY if written_count > 0
                if written_count > 0 and SOCKETIO_AVAILABLE:
                    try:
                        # Use asyncio.run to properly await the async emit in sync context
                        asyncio.run(sio.emit("emails_updated", {
                            "count": written_count,
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                        emitted = True
                        print(f"[WORKER] Socket.IO event emitted: emails_updated (count={written_count})")
                    except Exception as e:
                        print(f"[WARN] [WORKER] Socket.IO emission failed: {e}")

            # WORKER-PERF-01: Save cursor after successful cycle
            if gmail_client and current_cursor:
                try:
                    control.store.set_sync_state(tenant_id, account_id, current_cursor)
                except Exception as e:
                    print(f"[WARN] [WORKER] Failed to save cursor: {e}")

            # Log final counters
            print(f"[WORKER] Counters: changed_ids_count={changed_ids_count}, fetched_emails_count={fetched_emails_count}, written_count={written_count}, emitted={emitted}")
            print("[WORKER] Cycle complete - sleeping 60s")
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
