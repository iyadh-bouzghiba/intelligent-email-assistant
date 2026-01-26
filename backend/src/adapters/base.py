"""
Universal Email Adapter Pattern

This module defines the base interface for email providers (Gmail, Outlook, etc.)
and the StandardEmail format that all adapters must return.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class StandardEmail(BaseModel):
    """
    Normalized email format that all adapters must return.
    This ensures consistent data structure regardless of the email provider.
    """
    id: str = Field(description="Unique email ID from the provider")
    sender: str = Field(description="Sender in format: 'Name <email@example.com>'")
    subject: str = Field(description="Email subject line")
    body_text: str = Field(description="Plain text body (HTML stripped)")
    timestamp: datetime = Field(description="When the email was sent")
    thread_id: str = Field(description="Thread/conversation ID")
    in_reply_to: Optional[str] = Field(default=None, description="ID of email this is replying to")
    recipients: List[str] = Field(default_factory=list, description="List of recipient emails")


class EmailProvider(ABC):
    """
    Abstract base class for email provider adapters.
    
    All email providers (Gmail, Outlook, etc.) must implement this interface
    to ensure consistent behavior across different email services.
    """
    
    @abstractmethod
    async def fetch_emails(
        self,
        since: datetime,
        max_results: int = 50
    ) -> List[StandardEmail]:
        """
        Fetch emails since a given timestamp.
        
        Args:
            since: Fetch emails received after this datetime
            max_results: Maximum number of emails to return
            
        Returns:
            List of StandardEmail objects
        """
        pass
    
    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None
    ) -> str:
        """
        Send an email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text or HTML)
            thread_id: Optional thread ID to reply to
            
        Returns:
            ID of the sent email
        """
        pass
    
    @abstractmethod
    async def setup_webhook(self, callback_url: str) -> dict:
        """
        Setup real-time push notifications for new emails.
        
        Args:
            callback_url: URL to receive webhook notifications
            
        Returns:
            Webhook configuration details
        """
        pass
    
    @abstractmethod
    async def refresh_credentials(self) -> bool:
        """
        Refresh OAuth2 credentials if expired.
        
        Returns:
            True if refresh successful, False otherwise
        """
        pass
