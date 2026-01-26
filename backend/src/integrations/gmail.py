import base64
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

class GmailClient:
    """
    Unified Gmail Client handling API interactions, Real-time Watch, and Message Fetching.
    Consolidates functionality from previous API Client and Adapter.
    """

    def __init__(self, token_data: Dict[str, Any]):
        """
        Initialize with OAuth2 token data.
        """
        if not token_data:
            raise ValueError("Missing OAuth token data")

        self.credentials = Credentials(
            token=token_data.get("token") or token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )

        self.service = build('gmail', 'v1', credentials=self.credentials, cache_discovery=False)

    def refresh_if_needed(self):
        """Checks and refreshes credentials if expired."""
        if self.credentials.expired:
            self.credentials.refresh(Request())
            # Re-build service
            self.service = build('gmail', 'v1', credentials=self.credentials, cache_discovery=False)

    # ------------------------------------------------------------------
    # WATCH (Push Notifications)
    # ------------------------------------------------------------------

    def start_watch(self, topic_name: str, label_ids: list = ["INBOX"]) -> Dict[str, Any]:
        """
        Registers a watch on the user's mailbox.
        Verified configuration: labelIds=['INBOX'], topicName=...
        """
        request = {
            'labelIds': label_ids,
            'topicName': topic_name
        }
        try:
            return self.service.users().watch(userId='me', body=request).execute()
        except HttpError as e:
             raise RuntimeError(f"Failed to start Gmail watch: {e}")

    def stop_watch(self):
        """Stops the current watch."""
        try:
            self.service.users().stop(userId='me').execute()
        except HttpError as e:
            # Ignore if already stopped/expired
            pass

    # ------------------------------------------------------------------
    # HISTORY & SYNC
    # ------------------------------------------------------------------

    def list_history(self, start_history_id: str) -> List[Dict[str, Any]]:
        """
        Fetch history of changes since start_history_id.
        Returns list of history records (used to find messageAdded events).
        """
        try:
            response = self.service.users().history().list(
                userId='me',
                startHistoryId=start_history_id,
                historyTypes=['messageAdded']
            ).execute()
            return response.get('history', [])
        except HttpError as e:
            if e.resp.status == 404:
                # History ID too old, requires full sync (not handled here, returning empty)
                return []
            raise RuntimeError(f"Failed to list history: {e}")

    # ------------------------------------------------------------------
    # MESSAGE FETCHING & PARSING
    # ------------------------------------------------------------------

    def get_message(self, message_id: str) -> Dict[str, Any]:
        """
        Fetches a single message and parses it into a clean dictionary
        compatible with the AI Engine's entry point.
        """
        try:
            msg = self.service.users().messages().get(
                userId='me', id=message_id, format='full'
            ).execute()
            return self._parse_message(msg)
        except HttpError as e:
            raise RuntimeError(f"Failed to fetch message {message_id}: {e}")

    def _parse_message(self, raw_msg: Dict[str, Any]) -> Dict[str, Any]:
        """Parses raw Gmail API response into a simplified dict."""
        payload = raw_msg.get('payload', {})
        headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}
        
        body_text, is_html = self._extract_body(payload)
        
        return {
            "message_id": raw_msg.get('id'),
            "thread_id": raw_msg.get('threadId'),
            "subject": headers.get('subject', '(No Subject)'),
            "sender": headers.get('from', 'Unknown'),
            "recipients": [headers.get('to', '')], # Simplified
            "body": body_text,
            "is_html": is_html,
            "timestamp": headers.get('date') # Could parse to datetime if needed
        }

    def _extract_body(self, payload: Dict[str, Any]) -> tuple:
        """Extracts body text, returns (text, is_html)."""
        body = ""
        is_html = False

        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode('utf-8')
                        return body, False # Prefer plain text
                elif part['mimeType'] == 'text/html':
                    data = part['body'].get('data')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode('utf-8')
                        is_html = True
        else:
            data = payload['body'].get('data')
            if data:
                body = base64.urlsafe_b64decode(data).decode('utf-8')
                if payload.get('mimeType') == 'text/html':
                    is_html = True

        if is_html:
            # Basic cleanup
            soup = BeautifulSoup(body, 'html.parser')
            body = soup.get_text(separator='\n')
            is_html = False # We converted it

        return body, is_html
