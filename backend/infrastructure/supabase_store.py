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

    def save_email(self, subject, sender, date, body=None, message_id=None, tenant_id="primary"):
        """
        Upserts an email into Supabase. 
        Deduplication is handled by (tenant_id, gmail_message_id) unique index.
        """
        payload = {
            "subject": subject,
            "sender": sender,
            "date": date,
            "body": body,
            "tenant_id": tenant_id,
            "created_at": datetime.utcnow().isoformat()
        }
        
        if message_id:
            payload["gmail_message_id"] = message_id
            return self.client.table("emails").upsert(
                payload, 
                on_conflict="tenant_id,gmail_message_id"
            ).execute()
        
        # Fallback to legacy deduplication if no message_id provided
        return self.client.table("emails").upsert(
            payload, 
            on_conflict="subject,date"
        ).execute()

    def get_emails(self, limit=50):
        """Fetches latest emails from the source of truth."""
        try:
            return self.client.table("emails") \
                .select("*") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
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
