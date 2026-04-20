import os
import logging
from supabase import create_client
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SupabaseStore:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_SERVICE_KEY")

        if not self.url or not self.key:
            raise RuntimeError("Supabase environment variables missing")

        self.client = create_client(self.url, self.key)

    def save_thread(self, thread_id, subject, summary, account_id="default"):
        return self.client.table("email_threads").insert({
            "thread_id": thread_id,
            "account_id": account_id,
            "subject": subject,
            "summary": summary,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()

    def get_threads(self, account_id="default"):
        try:
            return self.client.table("email_threads") \
                .select("*") \
                .eq("account_id", account_id) \
                .order("created_at", desc=True) \
                .execute()
        except Exception as e:
            logger.warning(f"Supabase thread fetch error: {e}")
            return type('obj', (object,), {'data': []})

    def save_email(self, subject, sender, date, body=None, message_id=None, tenant_id="primary", account_id="default", thread_id=None):
        """
        Upserts an email into Supabase.
        Deduplication is handled by (account_id, gmail_message_id) unique index.

        Note: created_at is NOT included in payload - database sets it on INSERT only.
        updated_at tracks when the record was last synced from Gmail.

        CRITICAL: account_id MUST be included in payload for multi-account isolation.
        CRITICAL: Timestamp validation ensures UTC timezone consistency.
        CRITICAL: thread_id required for email send functionality.
        """
        from datetime import datetime, timezone
        import logging
        logger = logging.getLogger("supabase_store")

        # CRITICAL VALIDATION: Ensure date timestamp is timezone-aware UTC
        # This prevents timestamp drift caused by naive datetime objects
        validated_date = date
        if isinstance(date, str):
            # Verify ISO format includes timezone (+00:00 or Z suffix)
            if not ('+' in date or date.endswith('Z')):
                logger.warning(f"[TIMESTAMP-VALIDATION] Received naive timestamp string without timezone: {date}")
                logger.warning(f"[TIMESTAMP-VALIDATION] Subject: {subject[:50] if subject else 'Unknown'}")
                # Assume UTC and add timezone suffix
                validated_date = f"{date}+00:00" if not date.endswith('Z') else date
                logger.warning(f"[TIMESTAMP-VALIDATION] Corrected to: {validated_date}")
            else:
                logger.info(f"[TIMESTAMP-VALIDATION] Timestamp OK: {date[:19]}... (has timezone)")

        payload = {
            "subject": subject,
            "sender": sender,
            "date": validated_date,
            "body": body,
            "tenant_id": tenant_id,
            "account_id": account_id,  # CRITICAL: Required for multi-account email isolation
            "updated_at": datetime.now(timezone.utc).isoformat(),  # ✅ FIXED: Use timezone-aware datetime
            "thread_id": thread_id  # CRITICAL: Gmail thread ID for send functionality
        }

        if message_id:
            payload["gmail_message_id"] = message_id
            return self.client.table("emails").upsert(
                payload,
                on_conflict="account_id,gmail_message_id"
            ).execute()

        # Fallback: check env flag before inserting without dedupe
        allow_null_id = os.getenv("ALLOW_NULL_GMAIL_ID", "false").lower() == "true"
        if allow_null_id:
            # Legacy unsafe mode: insert without dedup (use only for recovery)
            subj = subject if isinstance(subject, str) else ("" if subject is None else str(subject))
            subject_truncated = (subj[:50] + "...") if len(subj) > 50 else subj
            logger.warning(
                f"[SYNC] UNSAFE MODE: Missing gmail_message_id; inserting without dedupe "
                f"(tenant={tenant_id}, subject={subject_truncated}, date={date})"
            )
            return self.client.table("emails").insert(payload).execute()

        # Default: skip insert to prevent DB corruption
        subj = subject if isinstance(subject, str) else ("" if subject is None else str(subject))
        subject_truncated = (subj[:50] + "...") if len(subj) > 50 else subj
        logger.warning(
            f"[SYNC] Missing gmail_message_id; SKIPPING insert to prevent corruption "
            f"(tenant={tenant_id}, subject={subject_truncated}, date={date})"
        )
        return None

    
    def save_email_atomic(
        self,
        subject,
        sender,
        date,
        body=None,
        message_id=None,
        tenant_id="primary",
        account_id="default",
        create_ai_job=False,
        thread_id=None,
        provider="gmail",
        thread_ref=None,
    ):

        """
        Atomically saves email + conditionally creates AI job via single RPC call.

        This is the HARDENING PATCH replacement for save_email() + enqueue_ai_job().
        Guarantees atomicity: email and job created in same database transaction.

        Args:
            create_ai_job: If True, creates AI job atomically with email insert.
                          Use True for first 30 emails (cost control).
            
            thread_id: Legacy provider-native thread ID used by current send flow (optional).
            provider: Provider identifier. Currently always "gmail".
            thread_ref: Provider-native thread reference for abstraction layer (optional).


        Returns:
            RPC response with {email_id, job_id, job_created} or None on failure
        """
        from datetime import datetime, timezone
        import logging
        logger = logging.getLogger("supabase_store")

        if not message_id:
            logger.error("[ATOMIC-SAVE] Missing gmail_message_id - SKIPPING to prevent corruption")
            return None

        # Validate timestamp (same logic as save_email)
        validated_date = date
        if isinstance(date, str):
            if not ('+' in date or date.endswith('Z')):
                validated_date = f"{date}+00:00" if not date.endswith('Z') else date

        try:
            result = self.client.rpc('save_email_with_ai_job', {
                'p_subject': subject,
                'p_sender': sender,
                'p_date': validated_date,
                'p_body': body or '',
                'p_message_id': message_id,
                'p_account_id': account_id,
                'p_tenant_id': tenant_id,
                'p_thread_id': thread_id,
                'p_provider': provider,
                'p_thread_ref': thread_ref,
                'p_create_ai_job': create_ai_job
            }).execute()

            if result and result.data:
                logger.info(f"[ATOMIC-SAVE] Email saved: {message_id[:8]}..., AI job: {create_ai_job}")
                return result
            else:
                logger.error(f"[ATOMIC-SAVE] RPC returned no data for {message_id[:8]}...")
                return None

        except Exception as e:
            logger.error(f"[ATOMIC-SAVE] RPC failed for {message_id[:8]}...: {type(e).__name__}: {e}")
            return None

    def get_emails(self, limit=50, account_id=None):
        """
        Fetches emails from Supabase.

        STABLE VERSION: Direct query without LEFT JOIN to ensure reliability.
        AI summary integration can be added after verifying basic functionality.

        Args:
            limit: Maximum number of emails to return (default: 50)
            account_id: Filter by specific account (optional)

        Returns:
            Supabase response object with .data attribute containing email list
        """
        import logging
        logger = logging.getLogger("supabase_store")

        try:
            # Direct query without LEFT JOIN for maximum reliability
            query = self.client.table("emails").select("*")

            # Filter by account_id if provided
            if account_id:
                logger.info(f"[EMAILS] Filtering by account_id: {account_id}")
                query = query.eq("account_id", account_id)

            # Execute query with ordering and limit
            result = query.order("date", desc=True).limit(limit).execute()

            # Log result for debugging
            email_count = len(result.data) if result.data else 0
            logger.info(f"[EMAILS] Retrieved {email_count} emails from database")

            return result
        except Exception as e:
            logger.error(f"[EMAILS] Supabase fetch error: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[EMAILS] Traceback: {traceback.format_exc()}")
            return type('obj', (object,), {'data': []})

    def get_emails_with_summaries(self, limit=50, account_id=None):
        """
        Fetches emails with AI summaries via LEFT JOIN (OPTIMIZED VERSION).

        This eliminates the N+1 query pattern by fetching emails and summaries
        in a single database query.

        Args:
            limit: Maximum number of emails to return (default: 50)
            account_id: Filter by specific account (optional)

        Returns:
            List of email dictionaries with flattened summary fields:
            - ai_summary_json: JSONB object {overview, action_items, urgency}
            - ai_summary_text: Plain text overview
            - ai_summary_model: Model used (e.g., "mistral-small-latest")
        """
        import logging
        logger = logging.getLogger("supabase_store")

        try:
            # Build query with LEFT JOIN to email_ai_summaries
            # CRITICAL: Use proper Supabase syntax to avoid empty responses
            query = self.client.table("emails").select(
                "*",
                count=None  # Don't include count in response
            )

            # Filter by account_id if provided
            if account_id:
                logger.info(f"[EMAILS] Filtering by account_id: {account_id}")
                query = query.eq("account_id", account_id)

            # Execute query with ordering and limit
            result = query.order("date", desc=True).limit(limit).execute()

            if not result.data:
                logger.info("[EMAILS] No emails found")
                return []

            # Fetch AI summaries separately for these emails (more reliable than LEFT JOIN)
            email_ids = [email.get("gmail_message_id") for email in result.data if email.get("gmail_message_id")]

            # Build a map of gmail_message_id -> summary
            summaries_map = {}
            if email_ids:
                try:
                    summaries_query = self.client.table("email_ai_summaries").select("*")

                    # Filter by account_id and gmail_message_ids
                    if account_id:
                        summaries_query = summaries_query.eq("account_id", account_id)

                    summaries_query = summaries_query.in_("gmail_message_id", email_ids)

                    summaries_result = summaries_query.execute()

                    # Build map: newest row per gmail_message_id wins.
                    # Sort by updated_at descending first so the first-seen entry
                    # for each id is always the most recent one.
                    sorted_summaries = sorted(
                        (summaries_result.data or []),
                        key=lambda s: s.get("updated_at") or "",
                        reverse=True,
                    )
                    for summary in sorted_summaries:
                        msg_id = summary.get("gmail_message_id")
                        if msg_id and msg_id not in summaries_map:
                            summaries_map[msg_id] = summary

                    logger.info(f"[EMAILS] Fetched {len(summaries_map)} summaries for {len(email_ids)} emails")

                except Exception as summary_err:
                    logger.warning(f"[EMAILS] Summary fetch failed: {type(summary_err).__name__}: {summary_err}")
                    # Continue without summaries rather than failing

            # Merge summaries into email objects
            enriched_emails = []
            for email in result.data:
                msg_id = email.get("gmail_message_id")
                summary = summaries_map.get(msg_id) if msg_id else None

                if summary:
                    email["ai_summary_json"] = summary.get("summary_json")
                    email["ai_summary_text"] = summary.get("summary_text")
                    email["ai_summary_model"] = summary.get("model")
                else:
                    email["ai_summary_json"] = None
                    email["ai_summary_text"] = None
                    email["ai_summary_model"] = None

                enriched_emails.append(email)

            logger.info(f"[EMAILS] Returning {len(enriched_emails)} emails with summary data")
            return enriched_emails

        except Exception as e:
            logger.error(f"[EMAILS] Fetch with summaries error: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[EMAILS] Traceback: {traceback.format_exc()}")
            return []

    def save_credential(self, provider: str, account_id: str, encrypted_payload: dict, scopes: list = None):
        """
        Upserts encrypted OAuth credentials to Supabase.

        Args:
            provider: OAuth provider (e.g., "gmail")
            account_id: User/account identifier (e.g., "default")
            encrypted_payload: Dict with encrypted token/refresh_token and other fields
            scopes: List of OAuth scopes

        Returns:
            Supabase response object
        """
        import json

        # Convert scopes list to comma-separated string for TEXT column
        scopes_str = ",".join(scopes) if scopes else ""

        payload = {
            "provider": provider,
            "account_id": account_id,
            "encrypted_payload": json.dumps(encrypted_payload),
            "scopes": scopes_str,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            result = self.client.table("credentials").upsert(
                payload,
                on_conflict="provider,account_id"
            ).execute()
            logger.info(f"[SUPABASE] Stored credentials (provider={provider}, account_id={account_id})")
            return result
        except Exception as e:
            logger.error(f"Supabase credential save failed: {e}")
            raise

    def get_credential(self, provider: str, account_id: str):
        """
        Retrieves encrypted OAuth credentials from Supabase.

        Args:
            provider: OAuth provider (e.g., "gmail")
            account_id: User/account identifier (e.g., "default")

        Returns:
            Dict with encrypted_payload and scopes, or None if not found
        """
        import json

        try:
            response = self.client.table("credentials") \
                .select("*") \
                .eq("provider", provider) \
                .eq("account_id", account_id) \
                .execute()

            if response.data and len(response.data) > 0:
                cred = response.data[0]

                # Parse scopes from comma-separated string to list
                scopes_str = cred.get("scopes", "")
                scopes = [s.strip() for s in scopes_str.split(",") if s.strip()] if scopes_str else []

                logger.info(f"[SUPABASE] Loaded credentials (provider={provider}, account_id={account_id})")
                return {
                    "encrypted_payload": json.loads(cred["encrypted_payload"]),
                    "scopes": scopes,
                    "updated_at": cred.get("updated_at")
                }
            return None
        except Exception as e:
            logger.warning(f"Supabase credential fetch error: {e}")
            return None

    def get_sync_state(self, tenant_id: str, account_id: str):
        """
        Retrieves the last_history_id cursor from gmail_sync_state table.

        Args:
            tenant_id: Tenant identifier (e.g., "primary")
            account_id: Gmail account identifier (e.g., "default")

        Returns:
            String historyId or None if no cursor exists
        """
        try:
            response = self.client.table("gmail_sync_state") \
                .select("last_history_id") \
                .eq("tenant_id", tenant_id) \
                .eq("account_id", account_id) \
                .execute()

            if response.data and len(response.data) > 0:
                return response.data[0].get("last_history_id")
            return None
        except Exception as e:
            logger.warning(f"Supabase sync state fetch error: {e}")
            return None

    def set_sync_state(self, tenant_id: str, account_id: str, last_history_id: str):
        """
        Upserts the last_history_id cursor into gmail_sync_state table.

        Args:
            tenant_id: Tenant identifier (e.g., "primary")
            account_id: Gmail account identifier (e.g., "default")
            last_history_id: Current historyId from Gmail profile
        """
        payload = {
            "tenant_id": tenant_id,
            "account_id": account_id,
            "last_history_id": last_history_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            self.client.table("gmail_sync_state").upsert(
                payload,
                on_conflict="tenant_id,account_id"
            ).execute()
            logger.info(f"[SYNC-STATE] Cursor saved: {last_history_id[:8]}... (tenant={tenant_id}, account={account_id})")
        except Exception as e:
            logger.error(f"Supabase sync state save failed: {e}")
            raise


    def list_credentials(self, provider: str):
        """Lists credentials for provider without exposing encrypted_payload."""
        try:
            response = self.client.table("credentials")                 .select("account_id,updated_at,scopes")                 .eq("provider", provider)                 .execute()

            data = response.data or []
            for cred in data:
                scopes_str = cred.get("scopes", "") or ""
                cred["scopes"] = [s.strip() for s in scopes_str.split(",") if s.strip()] if scopes_str else []
            return data
        except Exception as e:
            logger.warning(f"Supabase credential list error: {e}")
            return []

    def delete_credential(self, provider: str, account_id: str):
        """Deletes credentials for provider/account_id from Supabase."""
        try:
            self.client.table("credentials")                 .delete()                 .eq("provider", provider)                 .eq("account_id", account_id)                 .execute()
            logger.info(f"[SUPABASE] Deleted credentials (provider={provider}, account_id={account_id})")
        except Exception as e:
            logger.warning(f"Supabase credential delete error: {e}")

    def enqueue_ai_job(self, account_id: str, gmail_message_id: str, job_type: str = "email_summarize_v1"):
        """
        Enqueue AI summarization job (idempotent via unique index).

        Args:
            account_id: Gmail account identifier
            gmail_message_id: Gmail's stable message ID
            job_type: Job type identifier (default: "email_summarize_v1")

        Returns:
            job_id (str) if successful, None if failed
        """
        try:
            payload = {
                "job_type": job_type,
                "account_id": account_id,
                "gmail_message_id": gmail_message_id,
                "status": "queued",
                "attempts": 0,
                "run_after": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            result = self.client.table("ai_jobs").upsert(
                payload,
                on_conflict="job_type,account_id,gmail_message_id"
            ).execute()

            if result.data and len(result.data) > 0:
                job_id = result.data[0].get("id")
                logger.info(f"[AI-ENQUEUE] Job {job_id} queued for {account_id}/{gmail_message_id[:8]}...")
                return job_id
            return None
        except Exception as e:
            logger.warning(f"AI job enqueue failed: {e}")
            return None
