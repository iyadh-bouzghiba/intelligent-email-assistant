import base64
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from email.mime.text import MIMEText

class GmailClient:
    """
    Unified Gmail Client handling API interactions, Real-time Watch, and Message Fetching.
    """

    def __init__(self, token_data: Dict[str, Any]):
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

        # cache_discovery=False is mandatory for Render
        self.service = build('gmail', 'v1', credentials=self.credentials, cache_discovery=False)

    def refresh_if_needed(self):
        """Checks and refreshes credentials if expired."""
        if self.credentials and self.credentials.expired and self.credentials.refresh_token:
            try:
                self.credentials.refresh(Request())
                self.service = build('gmail', 'v1', credentials=self.credentials, cache_discovery=False)
            except Exception as e:
                print(f"[WARN] Failed to refresh token: {e}")

    def start_watch(self, topic_name: str, label_ids: list = ["INBOX"]) -> Dict[str, Any]:
        request = {'labelIds': label_ids, 'topicName': topic_name}
        try:
            return self.service.users().watch(userId='me', body=request).execute()
        except HttpError as e:
             raise RuntimeError(f"Failed to start Gmail watch: {e}")

    def stop_watch(self):
        try:
            self.service.users().stop(userId='me').execute()
        except HttpError as e:
            pass

    def list_history(self, start_history_id: str) -> List[Dict[str, Any]]:
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

    def get_message(self, message_id: str) -> Dict[str, Any]:
        try:
            msg = self.service.users().messages().get(
                userId='me', id=message_id, format='full'
            ).execute()
            return self._parse_message(msg)
        except HttpError as e:
            raise RuntimeError(f"Failed to fetch message {message_id}: {e}")

    def _parse_message(self, raw_msg: Dict[str, Any]) -> Dict[str, Any]:
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
        try:
            missing_padding = len(data) % 4
            if missing_padding:
                data += '=' * (4 - missing_padding)
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        except Exception:
            return ""

    def _extract_body(self, payload: Dict[str, Any]) -> tuple:
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

    def get_thread_latest_inbound_message(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch the latest INBOUND (non-SENT) message from a Gmail thread.
        CRITICAL: Filters out SENT messages to prevent self-reply loops.

        Args:
            thread_id: Gmail thread ID

        Returns:
            dict with: gmail_message_id, subject, from, reply_to (if present)
            None if thread not found or no inbound messages

        Raises:
            RuntimeError: If Gmail API call fails
        """
        try:
            # Fetch thread with all messages (need labelIds to filter SENT)
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='metadata',
                metadataHeaders=['From', 'Reply-To', 'Subject', 'Message-ID']
            ).execute()

            messages = thread.get('messages', [])
            if not messages:
                return None

            # CRITICAL: Filter to inbound messages only (exclude SENT)
            # This prevents replying to own sent messages (self-reply loop)
            inbound_messages = [
                m for m in messages
                if 'SENT' not in m.get('labelIds', [])
            ]

            if not inbound_messages:
                # No inbound messages found (thread only contains sent messages)
                return None

            # Get the latest inbound message (last in filtered list)
            latest_inbound = inbound_messages[-1]

            # Extract headers
            payload = latest_inbound.get('payload', {})
            headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}

            return {
                'gmail_message_id': latest_inbound.get('id', ''),
                'subject': headers.get('subject', '(No Subject)'),
                'from': headers.get('from', ''),
                'reply_to': headers.get('reply-to', '')
            }
        except HttpError as e:
            if e.resp.status == 404:
                return None
            raise RuntimeError(f"Failed to fetch thread {thread_id}: {e}")

    def get_reply_headers(self, parent_message_id: str) -> Dict[str, Any]:
        """
        Fetch RFC-compliant reply headers from a parent message.

        Args:
            parent_message_id: Gmail message ID (stored in DB as gmail_message_id)

        Returns:
            dict with: rfc_message_id, reply_to, references, in_reply_to, subject, thread_id

        Raises:
            RuntimeError: If Gmail API call fails
        """
        try:
            # Fetch full message to access all headers
            raw_msg = self.service.users().messages().get(
                userId='me',
                id=parent_message_id,
                format='full'
            ).execute()

            # Extract headers
            payload = raw_msg.get('payload', {})
            headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}

            # Extract RFC Message-ID (CRITICAL: different from Gmail message_id)
            rfc_message_id = headers.get('message-id', '')

            # Determine reply-to address (fallback to From if Reply-To not present)
            reply_to = headers.get('reply-to', headers.get('from', ''))

            # Build References header (append parent's Message-ID to existing References)
            existing_references = headers.get('references', '').strip()
            if existing_references and rfc_message_id:
                references = f"{existing_references} {rfc_message_id}"
            elif rfc_message_id:
                references = rfc_message_id
            else:
                references = ''

            # In-Reply-To should be parent's Message-ID
            in_reply_to = rfc_message_id

            # Extract subject for "Re:" prefix handling
            subject = headers.get('subject', '(No Subject)')

            # Extract Gmail threadId for Gmail-native threading
            thread_id = raw_msg.get('threadId', '')

            return {
                'rfc_message_id': rfc_message_id,
                'reply_to': reply_to,
                'references': references,
                'in_reply_to': in_reply_to,
                'subject': subject,
                'thread_id': thread_id
            }
        except HttpError as e:
            raise RuntimeError(f"Failed to fetch reply headers for {parent_message_id}: {e}")

    def set_thread_read_state(self, thread_id: str, is_read: bool) -> None:
        """
        Mark a Gmail thread as read or unread using the canonical thread-level API.

        Uses threads().modify() which operates on the full thread in a single call,
        matching Gmail's own thread-level read/unread UX behavior.

        Requires gmail.modify scope.

        Args:
            thread_id: Gmail thread ID
            is_read: True → remove UNREAD label; False → add UNREAD label

        Raises:
            RuntimeError: If Gmail API call fails
        """
        try:
            if is_read:
                body = {'removeLabelIds': ['UNREAD'], 'addLabelIds': []}
            else:
                body = {'addLabelIds': ['UNREAD'], 'removeLabelIds': []}
            self.service.users().threads().modify(
                userId='me', id=thread_id, body=body
            ).execute()
        except HttpError as e:
            raise RuntimeError(f"Failed to set read state for thread {thread_id}: {e}")

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        gmail_thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
        cc: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an email via Gmail API with RFC-compliant threading headers.

        Args:
            to: Recipient email address
            subject: Email subject (will normalize "Re:" prefix)
            body: Plain-text email body (UTF-8)
            gmail_thread_id: Gmail threadId for Gmail-native threading (optional)
            in_reply_to: RFC Message-ID of parent message (optional)
            references: RFC References header value (optional)

        Returns:
            dict with: success (bool), message_id (str), thread_id (str), error (str|None)
        """
        try:
            # Normalize subject with "Re:" prefix
            normalized_subject = subject
            if subject and not subject.lower().startswith('re:'):
                normalized_subject = f"Re: {subject}"

            # Build RFC-compliant MIME message
            message = MIMEText(body, 'plain', 'utf-8')
            message['To'] = to
            message['Subject'] = normalized_subject
            if cc:
                message['Cc'] = cc

            # Add threading headers if provided
            if in_reply_to:
                message['In-Reply-To'] = in_reply_to
            if references:
                message['References'] = references

            # Encode message for Gmail API
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            # Build request body
            send_body = {'raw': raw_message}
            if gmail_thread_id:
                send_body['threadId'] = gmail_thread_id

            # Send via Gmail API
            result = self.service.users().messages().send(
                userId='me',
                body=send_body
            ).execute()

            return {
                'success': True,
                'message_id': result.get('id', ''),
                'thread_id': result.get('threadId', ''),
                'error': None
            }
        except HttpError as e:
            return {
                'success': False,
                'message_id': '',
                'thread_id': '',
                'error': f"Gmail API error: {str(e)}"
            }
        except Exception as e:
            return {
                'success': False,
                'message_id': '',
                'thread_id': '',
                'error': f"Unexpected error: {str(e)}"
            }