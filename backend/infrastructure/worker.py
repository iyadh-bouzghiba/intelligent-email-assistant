import os
import sys
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.infrastructure.control_plane import ControlPlane
from backend.providers.registry import get_provider

# Schema mismatch retry configuration
MAX_SCHEMA_RETRIES = 5
SCHEMA_RETRY_DELAY = 300  # 5 minutes between retry attempts

# Configure logger for worker process
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(levelname)s] [%(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = True

# Socket.IO for realtime notifications
try:
    from backend.api.service import sio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    logger.warning("[WORKER] Socket.IO not available - realtime updates disabled")

# Shared operational heartbeat - accessible by health check server
WORKER_HEARTBEAT = {"last_cycle": None}



def _fetch_account_records(
    control: ControlPlane,
    tenant_id: str,
) -> List[Dict[str, Optional[str]]]:

    """
    Provider-aware account enumeration from credentials table.

    Tries to read delta_cursor directly from credentials.
    Falls back gracefully if the runtime DB does not yet have that column.
    """
    try:
        response = (
            control.store.client.table("credentials")
            .select("account_id,provider,delta_cursor,updated_at,scopes")
            .execute()
        )
    except Exception as e:
        logger.warning(
            f"[WORKER] Credential query with delta_cursor failed: {e}. "
            f"Falling back to query without delta_cursor."
        )
        response = (
            control.store.client.table("credentials")
            .select("account_id,provider,updated_at,scopes")
            .execute()
        )

    records: List[Dict[str, Optional[str]]] = []
    for row in (response.data or []):
        account_id = row.get("account_id")
        if not account_id:
            logger.warning("[WORKER] Skipping credential record with missing account_id")
            continue

        provider_name = (row.get("provider") or "gmail").strip().lower()

        
        delta_cursor = row.get("delta_cursor")

        if not delta_cursor:
            try:
                delta_cursor = control.store.get_sync_state(tenant_id, account_id)
            except Exception as e:
                logger.warning(
                    f"[WORKER] [{account_id}] Failed to load legacy gmail_sync_state cursor: {e}"
                )
                delta_cursor = None

        records.append(
            {
                "account_id": account_id,
                "provider": provider_name,
                "delta_cursor": delta_cursor,
            }
        )


    return records


def _save_delta_cursor(
    control: ControlPlane,
    provider_name: str,
    account_id: str,
    delta_cursor: Optional[str],
) -> None:
    if not delta_cursor:
        return

    try:
        (
            control.store.client.table("credentials")
            .update(
                {
                    "delta_cursor": delta_cursor,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("provider", provider_name)
            .eq("account_id", account_id)
            .execute()
        )
        logger.info(
            f"[WORKER] [{account_id}] Saved delta_cursor for provider={provider_name}: "
            f"{delta_cursor[:8]}..."
        )
    except Exception as e:
        logger.warning(
            f"[WORKER] [{account_id}] Failed to save delta_cursor for provider={provider_name}: {e}"
        )


def _sync_one_account(
    account_id: str,
    provider_name: str,
    last_cursor: Optional[str],
    control: ControlPlane,
    tenant_id: str,
) -> None:
    """
    Run one sync cycle for a single account using provider abstraction.

    Safe: all per-account exceptions are caught internally.
    A failure here must not halt other accounts.
    """
    logger.info(f"[WORKER] [{account_id}] Starting account sync (provider={provider_name})")

    try:
        provider = get_provider(provider_name, control.store, None)
    except ValueError as e:
        logger.error(f"[WORKER] [{account_id}] {e}")
        return

    changed_ids_count = 0
    fetched_emails_count = 0
    written_count = 0
    emitted = False
    current_cursor = last_cursor
    emails = []

    try:
        emails, current_cursor = provider.get_delta_emails(account_id, last_cursor)
    except RuntimeError as e:
        error_text = str(e)

        if "invalid_grant" in error_text:
            logger.warning(
                f"[WORKER] [{account_id}] Provider auth invalid for provider={provider_name}. "
                f"Re-auth required."
            )
            return

        if "auth_required" in error_text:
            logger.warning(
                f"[WORKER] [{account_id}] No valid token for provider={provider_name} - skipping account"
            )
            return

        logger.warning(
            f"[WORKER] [{account_id}] Provider sync failed for provider={provider_name}: {e}"
        )
        return

    if not last_cursor:
        logger.info(
            f"[WORKER] [{account_id}] First run (NULL cursor) for provider={provider_name}. "
            f"Bounded full sync returned {len(emails)} email(s)."
        )
    elif current_cursor and last_cursor == current_cursor and not emails:
        logger.info(
            f"[WORKER] [{account_id}] NO-OP: cursor unchanged for provider={provider_name} "
            f"({current_cursor[:8]}...)."
        )
        return
    else:
        fetched_emails_count = len(emails)
        changed_ids_count = fetched_emails_count
        logger.info(
            f"[WORKER] [{account_id}] Provider delta/full sync returned "
            f"{fetched_emails_count} email(s) for provider={provider_name}."
        )

    if emails:
        max_emails = control.max_emails_per_cycle()
        if len(emails) > max_emails:
            logger.warning(
                f"[WORKER] [{account_id}] Truncating cycle from {len(emails)} to {max_emails} emails "
                f"(policy enforcement)"
            )
            emails = emails[:max_emails]

        logger.info(
            f"[WORKER] [{account_id}] Fetch success via provider={provider_name}: {len(emails)} emails"
        )
    else:
        logger.info(
            f"[WORKER] [{account_id}] No new emails found via provider={provider_name}"
        )

    if emails:
        existing_message_ids = set()
        try:
            existing_result = (
                control.store.client.table("emails")
                .select("gmail_message_id")
                .eq("account_id", account_id)
                .execute()
            )
            if existing_result and existing_result.data:
                existing_message_ids = {
                    row["gmail_message_id"]
                    for row in existing_result.data
                    if row.get("gmail_message_id")
                }
                logger.info(
                    f"[WORKER] [{account_id}] Found {len(existing_message_ids)} existing emails in DB"
                )
        except Exception as e:
            logger.warning(f"[WORKER] [{account_id}] Could not query existing emails: {e}")

        ai_job_count = 0
        batch_size = 25

        for i in range(0, len(emails), batch_size):
            batch = emails[i : i + batch_size]

            for email in batch:
                m_id = email.message_id

                if not m_id:
                    logger.warning(
                        f"[WORKER] [{account_id}] SKIP: Missing message_id for subject: {email.subject}"
                    )
                    continue

                date_val = email.date or datetime.now(timezone.utc).isoformat()

                is_new_email = m_id not in existing_message_ids
                create_ai_job = is_new_email and ai_job_count < 20
                new_or_existing = "NEW" if is_new_email else "existing"

                logger.info(
                    f"[WORKER] [{account_id}] Ingesting ({new_or_existing}) via provider={provider_name}: "
                    f"{email.subject} (message_id={m_id})"
                )

                result = control.store.save_email_atomic(
                    subject=email.subject or "No Subject",
                    sender=email.sender or "Unknown",
                    date=date_val,
                    body=email.body or "",
                    message_id=m_id,
                    tenant_id=tenant_id,
                    account_id=account_id,
                    create_ai_job=create_ai_job,
                    thread_id=email.thread_id,
                )
                written_count += 1

                if result and result.data:
                    job_was_created = (
                        create_ai_job
                        and result.data.get("job_created")
                        and not result.data.get("job_existed")
                    )
                    if job_was_created:
                        ai_job_count += 1

            if i + batch_size < len(emails):
                logger.info(
                    f"[WORKER] [{account_id}] Batch commit complete. Cooling for 500ms..."
                )
                time.sleep(0.5)

        control.log_audit(
            "ingestion_complete",
            "provider_ingest",
            {
                "account_id": account_id,
                "provider": provider_name,
                "count": written_count,
                "ai_jobs": ai_job_count,
            },
        )
        logger.info(
            f"[WORKER] [{account_id}] Write complete for provider={provider_name}: "
            f"{written_count} email(s) ingested, {ai_job_count} AI job(s) created"
        )

        if written_count > 0 and SOCKETIO_AVAILABLE:
            try:
                asyncio.run(
                    sio.emit(
                        "emails_updated",
                        {
                            "count": written_count,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                )
                emitted = True
                logger.info(
                    f"[WORKER] [{account_id}] Socket.IO event emitted: emails_updated "
                    f"(count={written_count})"
                )
            except Exception as e:
                logger.warning(f"[WORKER] [{account_id}] Socket.IO emission failed: {e}")

    if current_cursor:
        _save_delta_cursor(control, provider_name, account_id, current_cursor)

    logger.info(
        f"[WORKER] [{account_id}] Counters: provider={provider_name}, "
        f"changed_ids_count={changed_ids_count}, fetched_emails_count={fetched_emails_count}, "
        f"written_count={written_count}, emitted={emitted}"
    )


def run_worker_loop():
    """
    Core background processing loop - iterates all connected accounts each cycle.
    Provider-aware orchestration with per-account cursor tracking.
    One account failure does not halt other accounts.
    """
    logger.info("[WORKER] Background worker loop initialized")
    control = ControlPlane()

    schema_retry_count = 0
    while schema_retry_count < MAX_SCHEMA_RETRIES:
        control.verify_schema()

        if ControlPlane.schema_state == "ok":
            break

        schema_retry_count += 1
        logger.warning(
            f"[WORKER] Schema verification failed (attempt {schema_retry_count}/{MAX_SCHEMA_RETRIES}). "
            f"State: {ControlPlane.schema_state}. "
            f"Retrying in {SCHEMA_RETRY_DELAY}s..."
        )

        WORKER_HEARTBEAT["last_cycle"] = time.time()
        WORKER_HEARTBEAT["schema_error_count"] = schema_retry_count

        time.sleep(SCHEMA_RETRY_DELAY)

    if ControlPlane.schema_state != "ok":
        logger.critical(
            f"[WORKER] Schema verification failed after {MAX_SCHEMA_RETRIES} attempts. "
            f"Final state: {ControlPlane.schema_state}. "
            f"Worker exiting cleanly for supervisor restart."
        )
        sys.exit(1)

    logger.info("[WORKER] Schema verification passed. Starting worker loop.")

    tenant_id = "primary"

    while True:
        try:
            WORKER_HEARTBEAT["last_cycle"] = time.time()

            if not control.is_worker_enabled():
                logger.info("[WORKER] Ingestion suspended by ControlPlane policy.")
                time.sleep(60)
                continue

            logger.info(f"[WORKER] Cycle started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            control.log_audit("cycle_start", "provider_ingest")

            try:
                account_records = _fetch_account_records(control, tenant_id)
            except Exception as e:
                logger.error(f"[WORKER] Failed to enumerate accounts: {e}. Skipping cycle.")
                time.sleep(60)
                continue

            if not account_records:
                logger.info("[WORKER] No connected accounts found. Sleeping 60s.")
                time.sleep(60)
                continue

            logger.info(f"[WORKER] Processing {len(account_records)} account(s) this cycle")

            for record in account_records:
                account_id = record.get("account_id")
                provider_name = record.get("provider") or "gmail"
                last_cursor = record.get("delta_cursor")

                if not account_id:
                    logger.warning("[WORKER] Skipping credential record with missing account_id")
                    continue

                try:
                    _sync_one_account(account_id, provider_name, last_cursor, control, tenant_id)
                except Exception as e:
                    logger.error(
                        f"[WORKER] [{account_id}] Unhandled error during sync for provider={provider_name}: {e}"
                    )

            logger.info("[WORKER] Cycle complete - sleeping 60s")
            time.sleep(60)

        except Exception as e:
            logger.error(f"[WORKER] ERROR: {e}")
            logger.info("[WORKER] Backing off 120s")
            time.sleep(120)


if __name__ == "__main__":
    WORKER_MODE = os.getenv("WORKER_MODE", "false").lower() == "true"
    if WORKER_MODE:
        run_worker_loop()
    else:
        logger.info("Worker mode disabled - safe exit")
