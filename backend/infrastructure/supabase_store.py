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
