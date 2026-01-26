"""
Outlook Adapter - Implements EmailProvider for Microsoft Graph API

Features:
- OAuth2 with MSAL (Microsoft Authentication Library)
- Microsoft Graph API integration
- Webhook support via Graph subscriptions
"""

from typing import List, Optional
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup

from .base import EmailProvider, StandardEmail


class OutlookAdapter(EmailProvider):
    """
    Outlook/Office365 email provider adapter.
    Uses Microsoft Graph API to access emails.
    """
    
    def __init__(self, access_token: str):
        """
        Initialize Outlook adapter with access token.
        
        Args:
            access_token: Microsoft Graph API access token
        """
        self.access_token = access_token
        self.graph_url = "https://graph.microsoft.com/v1.0"
    
    async def fetch_emails(
        self,
        since: datetime,
        max_results: int = 50
    ) -> List[StandardEmail]:
        """
        Fetch emails from Outlook via Microsoft Graph API.
        
        Args:
            since: Fetch emails after this datetime
            max_results: Maximum number of emails to return
            
        Returns:
            List of StandardEmail objects
        """
        try:
            # Format datetime for Graph API filter
            filter_date = since.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            url = f"{self.graph_url}/me/messages"
            params = {
                '$filter': f"receivedDateTime ge {filter_date}",
                '$top': max_results,
                '$orderby': 'receivedDateTime DESC'
            }
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        messages = data.get('value', [])
                        
                        return [self._convert_to_standard(msg) for msg in messages]
                    else:
                        print(f"[Outlook] Error fetching emails: {response.status}")
                        return []
        except Exception as e:
            print(f"[Outlook] Error: {e}")
            return []
    
    def _convert_to_standard(self, outlook_message: dict) -> StandardEmail:
        """Convert Microsoft Graph message to StandardEmail format."""
        # Extract body text
        body_content = outlook_message.get('body', {})
        body_text = body_content.get('content', '')
        
        # Convert HTML to plain text if needed
        if body_content.get('contentType') == 'html':
            body_text = self._html_to_text(body_text)
        
        # Parse timestamp
        timestamp = datetime.fromisoformat(
            outlook_message['receivedDateTime'].replace('Z', '+00:00')
        )
        
        # Extract sender
        sender_obj = outlook_message.get('from', {}).get('emailAddress', {})
        sender = f"{sender_obj.get('name', 'Unknown')} <{sender_obj.get('address', '')}>"
        
        # Extract recipients
        recipients = [
            r['emailAddress']['address']
            for r in outlook_message.get('toRecipients', [])
        ]
        
        return StandardEmail(
            id=outlook_message['id'],
            sender=sender,
            subject=outlook_message.get('subject', '(No Subject)'),
            body_text=body_text,
            timestamp=timestamp,
            thread_id=outlook_message.get('conversationId', outlook_message['id']),
            in_reply_to=outlook_message.get('internetMessageId'),
            recipients=recipients
        )
    
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
        """Send an email via Microsoft Graph API."""
        try:
            url = f"{self.graph_url}/me/sendMail"
            
            message = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "Text",
                        "content": body
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": to
                            }
                        }
                    ]
                }
            }
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=message) as response:
                    if response.status == 202:
                        return "sent"  # Graph API doesn't return message ID for sent emails
                    else:
                        raise Exception(f"Failed to send email: {response.status}")
        except Exception as e:
            print(f"[Outlook] Error sending email: {e}")
            raise
    
    async def setup_webhook(self, callback_url: str) -> dict:
        """Setup Microsoft Graph subscription for push notifications."""
        try:
            url = f"{self.graph_url}/subscriptions"
            
            subscription = {
                "changeType": "created",
                "notificationUrl": callback_url,
                "resource": "/me/mailFolders('Inbox')/messages",
                "expirationDateTime": (
                    datetime.utcnow() + timedelta(days=3)
                ).isoformat() + "Z",
                "clientState": "secretClientValue"
            }
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=subscription) as response:
                    if response.status == 201:
                        return await response.json()
                    else:
                        raise Exception(f"Failed to create subscription: {response.status}")
        except Exception as e:
            print(f"[Outlook] Error setting up webhook: {e}")
            raise
    
    async def refresh_credentials(self) -> bool:
        """
        Refresh OAuth2 credentials.
        Note: This requires MSAL library and client credentials.
        """
        # TODO: Implement MSAL token refresh
        print("[Outlook] Token refresh not yet implemented")
        return False


from datetime import timedelta  # Add missing import
