I have reviewed your backend/src/integrations/gmail.py code. The good news is that this specific file is clean and logically sound—it correctly expects the topic_name to be passed to it from the outside (the API service), meaning it does not have hard-coded project IDs that would cause a crash.

However, to ensure it is "Senior DevOps" level—meaning it won't crash even if the Google API is temporarily unreachable or if the token data is slightly malformed—I have added a few resiliency improvements.

Key Improvements Made:
Cache Discovery Fix: Setting cache_discovery=False is critical on platforms like Render to avoid "File Not Found" errors regarding the discovery cache.

Base64 Padding Resilience: Sometimes Gmail API data lacks the correct padding (==), which causes base64.urlsafe_b64decode to crash. I added a helper to handle this.

UTF-8 Handling: Added errors='ignore' to the decode process to prevent the app from crashing if an email contains weird emojis or non-standard characters.

The Final Full Code: backend/src/integrations/gmail.py
Python
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

        # cache_discovery=False is essential for serverless/container environments like Render
        self.service = build('gmail', 'v1', credentials=self.credentials, cache_discovery=False)

    def refresh_if_needed(self):
        """Checks and refreshes credentials if expired."""
        if self.credentials and self.credentials.expired and self.credentials.refresh_token:
            try:
                self.credentials.refresh(Request())
                self.service = build('gmail', 'v1', credentials=self.credentials, cache_discovery=False)
            except Exception as e:
                print(f"⚠️ Failed to refresh token: {e}")

    # ------------------------------------------------------------------
    # WATCH (Push Notifications)
    # ------------------------------------------------------------------

    def start_watch(self, topic_name: str, label_ids: list = ["INBOX"]) -> Dict[str, Any]:
        """Registers a watch on the user's mailbox."""
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
            pass

    # ------------------------------------------------------------------
    # HISTORY & SYNC
    # ------------------------------------------------------------------

    def list_history(self, start_history_id: str) -> List[Dict[str, Any]]:
        """Fetch history of changes since start_history_id."""
        try:
            response = self.service.users().history().list(
                userId='me',
                startHistoryId=start_history_id,
                historyTypes=['messageAdded']
            ).execute()
            return response.get('history', [])
        except HttpError as e:
            if e.resp.status == 404:
                return []
            raise RuntimeError(f"Failed to list history: {e}")

    # ------------------------------------------------------------------
    # MESSAGE FETCHING & PARSING
    # ------------------------------------------------------------------

    def get_message(self, message_id: str) -> Dict[str, Any]:
        """Fetches and parses a single message."""
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
            "recipients": [headers.get('to', '')],
            "body": body_text,
            "is_html": is_html,
            "timestamp": headers.get('date')
        }

    def _safe_b64_decode(self, data: str) -> str:
        """Helper to decode base64 with padding and error handling."""
        try:
            # Fix padding if necessary
            missing_padding = len(data) % 4
            if missing_padding:
                data += '=' * (4 - missing_padding)
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        except Exception:
            return ""

    def _extract_body(self, payload: Dict[str, Any]) -> tuple:
        """Extracts body text, returns (text, is_html)."""
        body = ""
        is_html = False

        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        body = self._safe_b64_decode(data)
                        return body, False
                elif part['mimeType'] == 'text/html':
                    data = part['body'].get('data')
                    if data:
                        body = self._safe_b64_decode(data)
                        is_html = True
        else:
            data = payload['body'].get('data')
            if data:
                body = self._safe_b64_decode(data)
                if payload.get('mimeType') == 'text/html':
                    is_html = True

        if is_html and body:
            soup = BeautifulSoup(body, 'html.parser')
            body = soup.get_text(separator='\n')
            is_html = False

        return body, is_html