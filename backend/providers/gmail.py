import base64
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.api.gmail_client import GmailClient as WorkerGmailClient
from backend.auth.credential_store import CredentialStore
from backend.core import EmailAssistant
from backend.data.store import PersistenceManager
from backend.integrations.gmail import GmailClient as RichGmailClient
from backend.providers.base import EmailProvider, NormalizedEmail
from backend.services.gmail_engine import get_message_body

logger = logging.getLogger(__name__)


class GmailProvider(EmailProvider):
    def __init__(self, supabase=None, security_manager=None):
        self.supabase = supabase
        self.security_manager = security_manager

    def _load_token_data(self, account_id: str) -> Dict[str, Any]:
        persistence = PersistenceManager()
        credential_store = CredentialStore(persistence)
        return credential_store.load_credentials(account_id) or {}

    def _build_worker_token_data(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "access_token": token_data.get("token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": token_data.get("client_id"),
            "client_secret": token_data.get("client_secret"),
            "scopes": token_data.get("scopes", []),
        }

    def _normalize_date(
        self,
        date_header: Optional[str],
        internal_date_ms: Optional[str],
    ) -> str:
        if date_header:
            try:
                parsed_dt = parsedate_to_datetime(date_header)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                return parsed_dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass

        if internal_date_ms:
            try:
                dt_utc = datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)
                return dt_utc.isoformat()
            except Exception:
                pass

        return datetime.now(timezone.utc).isoformat()

    def _normalize_assistant_email(self, email: Dict[str, Any]) -> NormalizedEmail:
        return NormalizedEmail(
            message_id=email.get("message_id") or email.get("id") or "",
            subject=email.get("subject", "No Subject"),
            sender=email.get("sender", "Unknown"),
            date=email.get("date") or datetime.now(timezone.utc).isoformat(),
            body=email.get("body", "") or "",
            thread_id=email.get("thread_id"),
        )

    def _normalize_raw_message(self, raw_msg: Dict[str, Any]) -> Optional[NormalizedEmail]:
        label_ids = raw_msg.get("labelIds", []) or []
        if "INBOX" not in label_ids:
            return None

        payload = raw_msg.get("payload", {})
        headers = payload.get("headers", [])

        subject = next(
            (h["value"] for h in headers if h["name"].lower() == "subject"),
            "No Subject",
        )
        sender = next(
            (h["value"] for h in headers if h["name"].lower() == "from"),
            "Unknown",
        )
        date_header = next(
            (h["value"] for h in headers if h["name"].lower() == "date"),
            None,
        )
        date_iso = self._normalize_date(date_header, raw_msg.get("internalDate"))

        raw_body = get_message_body(payload)
        cleaned_body = (raw_body or "").strip()

        return NormalizedEmail(
            message_id=raw_msg.get("id", ""),
            subject=subject,
            sender=sender,
            date=date_iso,
            body=cleaned_body,
            thread_id=raw_msg.get("threadId"),
        )

    def _extract_message_ids_from_history(
        self,
        history_records: List[Dict[str, Any]],
    ) -> List[str]:
        message_ids: List[str] = []
        seen = set()

        for record in history_records or []:
            for msg_added in record.get("messagesAdded", []):
                msg_id = msg_added.get("message", {}).get("id")
                if msg_id and msg_id not in seen:
                    seen.add(msg_id)
                    message_ids.append(msg_id)

        return message_ids

    def _run_bounded_full_sync(self, account_id: str) -> List[NormalizedEmail]:
        assistant = EmailAssistant(account_id=account_id, enable_summary=False)
        emails = assistant.process_emails()

        if isinstance(emails, dict) and emails.get("__auth_error__") == "invalid_grant":
            raise RuntimeError("invalid_grant")

        if not emails or isinstance(emails, dict):
            return []

        normalized: List[NormalizedEmail] = []
        for email in emails:
            item = self._normalize_assistant_email(email)
            if item.message_id:
                normalized.append(item)

        return normalized

    def get_delta_emails(
        self,
        account_id: str,
        cursor: Optional[str],
    ) -> Tuple[List[NormalizedEmail], Optional[str]]:
        token_data = self._load_token_data(account_id)
        if not token_data or "token" not in token_data:
            raise RuntimeError("auth_required")

        gmail_client = WorkerGmailClient(self._build_worker_token_data(token_data))
        current_cursor = gmail_client.get_current_history_id()

        if not current_cursor:
            raise RuntimeError("current_cursor_missing")

        # First run -> bounded full sync
        if not cursor:
            emails = self._run_bounded_full_sync(account_id)
            return emails, current_cursor

        # No-op
        if cursor == current_cursor:
            return [], current_cursor

        history_records = gmail_client.list_history(
            start_history_id=cursor,
            history_types=["messageAdded"],
        )

        # Cursor too old -> fallback to bounded full sync
        if history_records is None:
            emails = self._run_bounded_full_sync(account_id)
            return emails, current_cursor

        message_ids = self._extract_message_ids_from_history(history_records)
        if not message_ids:
            return [], current_cursor

        normalized: List[NormalizedEmail] = []
        for message_id in message_ids:
            raw_msg = gmail_client.get_message(message_id)
            item = self._normalize_raw_message(raw_msg)
            if item and item.message_id:
                normalized.append(item)

        return normalized, current_cursor

    def get_attachment(
        self,
        account_id: str,
        message_id: str,
        attachment_id: str,
    ) -> Tuple[bytes, str]:
        token_data = self._load_token_data(account_id)
        if not token_data or "token" not in token_data:
            raise RuntimeError("auth_required")

        gmail_client = WorkerGmailClient(self._build_worker_token_data(token_data))
        raw_attachment = (
            gmail_client.service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )

        data = raw_attachment.get("data", "")
        if data and len(data) % 4:
            data += "=" * (4 - (len(data) % 4))

        content = base64.urlsafe_b64decode(data.encode("utf-8")) if data else b""
        return content, "application/octet-stream"

    def send_email(
        self,
        account_id: str,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str],
    ) -> str:
        token_data = self._load_token_data(account_id)
        if not token_data or "token" not in token_data:
            raise RuntimeError("auth_required")

        gmail_client = RichGmailClient(token_data)
        gmail_client.refresh_if_needed()

        result = gmail_client.send_message(
            to=to,
            subject=subject,
            body=body,
            gmail_thread_id=thread_id,
        )

        if not result.get("success"):
            raise RuntimeError(result.get("error") or "send_email_failed")

        return result.get("message_id", "")

    def refresh_token(self, account_id: str) -> None:
        token_data = self._load_token_data(account_id)
        if not token_data or "token" not in token_data:
            raise RuntimeError("auth_required")

        gmail_client = RichGmailClient(token_data)
        gmail_client.refresh_if_needed()
