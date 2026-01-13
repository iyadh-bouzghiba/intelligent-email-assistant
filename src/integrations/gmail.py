import base64
from typing import List, Dict, Any, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

class GmailClient:
    """
    Enhanced Gmail client with automatic token refresh and defensive error handling.
    """
    def __init__(self, credentials_info: Dict[str, Any]):
        self.creds = Credentials.from_authorized_user_info(credentials_info)
        # Automatically refresh if expired
        if not self.creds.valid:
            if self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
        
        self.service = build('gmail', 'v1', credentials=self.creds)

    def get_latest_unread(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """Fetches a list of unread messages with explicit error handling."""
        try:
            results = self.service.users().messages().list(
                userId='me', q='is:unread', maxResults=max_results
            ).execute()
            return results.get('messages', [])
        except HttpError as error:
            # Handle specific API errors (e.g., token revoked)
            if error.resp.status == 401:
                raise Exception("Authentication expired or revoked. Please re-login.")
            print(f"Gmail API Error: {error}")
            return []

    def get_email_by_id(self, message_id: str) -> Dict[str, Any]:
        return self.service.users().messages().get(
            userId='me', id=message_id, format='full'
        ).execute()

    def get_thread_by_id(self, thread_id: str) -> Dict[str, Any]:
        return self.service.users().threads().get(
            userId='me', id=thread_id
        ).execute()

    @staticmethod
    def parse_body(message: Dict[str, Any]) -> str:
        """Robustly extracts plain text from multi-part Gmail payloads."""
        payload = message.get('payload', {})
        
        def extract(parts):
            for part in parts:
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8')
                if 'parts' in part:
                    res = extract(part['parts'])
                    if res: return res
            return None

        body = extract([payload]) if 'parts' not in payload else extract(payload['parts'])
        if not body and payload.get('body', {}).get('data'):
             # Fallback for simple structures
             body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
             
        return body or ""
