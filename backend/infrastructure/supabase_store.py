import os
from supabase import create_client
from datetime import datetime

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
            "created_at": datetime.utcnow().isoformat()
        }).execute()

    def get_threads(self, account_id="default"):
        try:
            return self.client.table("email_threads") \
                .select("*") \
                .eq("account_id", account_id) \
                .order("created_at", desc=True) \
                .execute()
        except Exception as e:
            print(f"[WARN] Supabase thread fetch error: {e}")
            return type('obj', (object,), {'data': []})

    def save_email(self, subject, sender, date, body=None, message_id=None, tenant_id="primary", account_id="default"):
        """
        Upserts an email into Supabase.
        Deduplication is handled by (account_id, gmail_message_id) unique index.

        Note: created_at is NOT included in payload - database sets it on INSERT only.
        updated_at tracks when the record was last synced from Gmail.

        CRITICAL: account_id MUST be included in payload for multi-account isolation.
        """
        payload = {
            "subject": subject,
            "sender": sender,
            "date": date,
            "body": body,
            "tenant_id": tenant_id,
            "account_id": account_id,  # CRITICAL: Required for multi-account email isolation
            "updated_at": datetime.utcnow().isoformat()
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
            print(
                f"[WARN] [SYNC] UNSAFE MODE: Missing gmail_message_id; inserting without dedupe "
                f"(tenant={tenant_id}, subject={subject_truncated}, date={date})"
            )
            return self.client.table("emails").insert(payload).execute()

        # Default: skip insert to prevent DB corruption
        subj = subject if isinstance(subject, str) else ("" if subject is None else str(subject))
        subject_truncated = (subj[:50] + "...") if len(subj) > 50 else subj
        print(
            f"[WARN] [SYNC] Missing gmail_message_id; SKIPPING insert to prevent corruption "
            f"(tenant={tenant_id}, subject={subject_truncated}, date={date})"
        )
        return None

    def get_emails(self, limit=50, account_id=None):
        """
        Fetches emails with AI summaries via LEFT JOIN.

        Returns emails with flattened summary fields:
        - ai_summary_json: JSONB object {overview, action_items, urgency}
        - ai_summary_text: Plain text overview
        - ai_summary_model: Model used (e.g., "mistral-small-latest")

        Args:
            limit: Maximum number of emails to return (default: 50)
            account_id: Filter by specific account (optional)
        """
        try:
            # LEFT JOIN with email_ai_summaries to include summaries if available
            query = self.client.table("emails").select(
                """
                *,
                email_ai_summaries!left(
                    summary_json,
                    summary_text,
                    model,
                    updated_at
                )
                """
            )

            # Filter by account_id if provided
            if account_id:
                query = query.eq("account_id", account_id)

            result = query.order("date", desc=True).limit(limit).execute()

            # Flatten joined data for frontend consumption
            if result.data:
                for email in result.data:
                    summaries = email.get("email_ai_summaries", [])
                    if summaries and len(summaries) > 0:
                        summary = summaries[0]
                        email["ai_summary_json"] = summary.get("summary_json")
                        email["ai_summary_text"] = summary.get("summary_text")
                        email["ai_summary_model"] = summary.get("model")
                    else:
                        email["ai_summary_json"] = None
                        email["ai_summary_text"] = None
                        email["ai_summary_model"] = None
                    # Remove nested array to keep response clean
                    del email["email_ai_summaries"]

            return result
        except Exception as e:
            print(f"[WARN] Supabase email fetch error: {e}")
            return type('obj', (object,), {'data': []})

    def save_credential(self, provider: str, account_id: str, encrypted_payload: dict, scopes: list = None):
        """
        Upserts encrypted OAuth credentials to Supabase.

        Args:
            provider: OAuth provider (e.g., "google")
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
            "updated_at": datetime.utcnow().isoformat()
        }

        try:
            result = self.client.table("credentials").upsert(
                payload,
                on_conflict="provider,account_id"
            ).execute()
            print(f"[OK] [SUPABASE] Stored credentials (provider={provider}, account_id={account_id})")
            return result
        except Exception as e:
            print(f"[ERROR] Supabase credential save failed: {e}")
            raise

    def get_credential(self, provider: str, account_id: str):
        """
        Retrieves encrypted OAuth credentials from Supabase.

        Args:
            provider: OAuth provider (e.g., "google")
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

                print(f"[OK] [SUPABASE] Loaded credentials (provider={provider}, account_id={account_id})")
                return {
                    "encrypted_payload": json.loads(cred["encrypted_payload"]),
                    "scopes": scopes,
                    "updated_at": cred.get("updated_at")
                }
            return None
        except Exception as e:
            print(f"[WARN] Supabase credential fetch error: {e}")
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
            print(f"[WARN] Supabase sync state fetch error: {e}")
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
            "updated_at": datetime.utcnow().isoformat()
        }

        try:
            self.client.table("gmail_sync_state").upsert(
                payload,
                on_conflict="tenant_id,account_id"
            ).execute()
            print(f"[OK] [SYNC-STATE] Cursor saved: {last_history_id[:8]}... (tenant={tenant_id}, account={account_id})")
        except Exception as e:
            print(f"[ERROR] Supabase sync state save failed: {e}")
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
            print(f"[WARN] Supabase credential list error: {e}")
            return []

    def delete_credential(self, provider: str, account_id: str):
        """Deletes credentials for provider/account_id from Supabase."""
        try:
            self.client.table("credentials")                 .delete()                 .eq("provider", provider)                 .eq("account_id", account_id)                 .execute()
            print(f"[OK] [SUPABASE] Deleted credentials (provider={provider}, account_id={account_id})")
        except Exception as e:
            print(f"[WARN] Supabase credential delete error: {e}")

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
                "run_after": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }

            result = self.client.table("ai_jobs").upsert(
                payload,
                on_conflict="job_type,account_id,gmail_message_id"
            ).execute()

            if result.data and len(result.data) > 0:
                job_id = result.data[0].get("id")
                print(f"[AI-ENQUEUE] Job {job_id} queued for {account_id}/{gmail_message_id[:8]}...")
                return job_id
            return None
        except Exception as e:
            print(f"[WARN] AI job enqueue failed: {e}")
            return None
