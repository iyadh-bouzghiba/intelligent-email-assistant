"""
Gmail Adapter - Implements EmailProvider for Gmail API

Features:
- OAuth2 with automatic token refresh
- HTML to plain text conversion
- Thread ID extraction
- Webhook support via Gmail Push API
"""

import base64
import re
from typing import List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import EmailProvider, StandardEmail


class GmailAdapter(EmailProvider):
    """
    Gmail email provider adapter.
    Normalizes Gmail API responses into StandardEmail format.
    """
    
    def __init__(self, credentials_dict: dict):
        """
        Initialize Gmail adapter with OAuth2 credentials.
        
        Args:
            credentials_dict: Dict containing token, refresh_token, client_id, client_secret
        """
        self.credentials = Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret')
        )
        self.service = build('gmail', 'v1', credentials=self.credentials)
    
    async def fetch_emails(
        self,
        since: datetime,
        max_results: int = 50
    ) -> List[StandardEmail]:
        """
        Fetch emails from Gmail since a given timestamp.
        
        Args:
            since: Fetch emails after this datetime
            max_results: Maximum number of emails to return
            
        Returns:
            List of StandardEmail objects
        """
        try:
            # Convert datetime to Gmail query format
            query = f'after:{int(since.timestamp())}'
            
            # List messages
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            standard_emails = []
            
            for msg in messages:
                # Get full message details
                full_msg = self.service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()
                
                standard_email = self._convert_to_standard(full_msg)
                if standard_email:
                    standard_emails.append(standard_email)
            
            return standard_emails
            
        except HttpError as e:
            print(f"[Gmail] Error fetching emails: {e}")
            return []
    
    def _convert_to_standard(self, gmail_message: dict) -> Optional[StandardEmail]:
        """Convert Gmail API message to StandardEmail format."""
        try:
            headers = {h['name']: h['value'] for h in gmail_message['payload']['headers']}
            
            # Extract body
            body_text = self._extract_body(gmail_message['payload'])
            
            # Parse timestamp
            timestamp = datetime.fromtimestamp(int(gmail_message['internalDate']) / 1000)
            
            return StandardEmail(
                id=gmail_message['id'],
                sender=headers.get('From', 'Unknown'),
                subject=headers.get('Subject', '(No Subject)'),
                body_text=body_text,
                timestamp=timestamp,
                thread_id=gmail_message['threadId'],
                in_reply_to=headers.get('In-Reply-To'),
                recipients=[headers.get('To', '')]
            )
        except Exception as e:
            print(f"[Gmail] Error converting message: {e}")
            return None
    
    def _extract_body(self, payload: dict) -> str:
        """Extract and clean email body from Gmail payload."""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break
                elif part['mimeType'] == 'text/html':
                    data = part['body'].get('data', '')
                    html = base64.urlsafe_b64decode(data).decode('utf-8')
                    body = self._html_to_text(html)
        else:
            data = payload['body'].get('data', '')
            if data:
                body = base64.urlsafe_b64decode(data).decode('utf-8')
        
        return body.strip()
    
    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text."""
        soup = BeautifulSoup(html, 'html.parser')
        return soup.get_text(separator='\n').strip()
    
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None
    ) -> str:
        """Send an email via Gmail API."""
        try:
            message = {
                'raw': base64.urlsafe_b64encode(
                    f"To: {to}\nSubject: {subject}\n\n{body}".encode()
                ).decode()
            }
            
            if thread_id:
                message['threadId'] = thread_id
            
            result = self.service.users().messages().send(
                userId='me',
                body=message
            ).execute()
            
            return result['id']
        except HttpError as e:
            print(f"[Gmail] Error sending email: {e}")
            raise
    
    async def setup_webhook(self, callback_url: str) -> dict:
        """Setup Gmail Push notifications."""
        try:
            request = {
                'labelIds': ['INBOX'],
                'topicName': callback_url  # Should be Pub/Sub topic
            }
            
            result = self.service.users().watch(
                userId='me',
                body=request
            ).execute()
            
            return result
        except HttpError as e:
            print(f"[Gmail] Error setting up webhook: {e}")
            raise
    
    async def refresh_credentials(self) -> bool:
        """Refresh OAuth2 credentials if expired."""
        try:
            if self.credentials.expired:
                from google.auth.transport.requests import Request
                self.credentials.refresh(Request())
                self.service = build('gmail', 'v1', credentials=self.credentials)
                return True
            return False
        except Exception as e:
            print(f"[Gmail] Error refreshing credentials: {e}")
            return False
