"""
Gmail Fetcher Service

Production-grade service for fetching and normalizing Gmail data.
Implements spam/trash filtering and thread grouping.
"""

from typing import List, Dict
from datetime import datetime, timedelta
from src.adapters.gmail import GmailAdapter
from src.adapters.base import StandardEmail


class GmailFetcherService:
    """
    Service for fetching emails from Gmail with production optimizations.
    
    Features:
    - Spam/trash filtering at source
    - Thread grouping
    - Bandwidth optimization
    - Error handling
    """
    
    def __init__(self, credentials: dict):
        """
        Initialize Gmail fetcher with user credentials.
        
        Args:
            credentials: OAuth2 credentials dict
        """
        self.adapter = GmailAdapter(credentials)
    
    async def fetch_recent_emails(
        self,
        limit: int = 10,
        days_back: int = 7
    ) -> List[StandardEmail]:
        """
        Fetch recent emails with spam/trash filtering.
        
        Args:
            limit: Maximum number of emails to fetch
            days_back: How many days back to fetch
            
        Returns:
            List of StandardEmail objects
        """
        # Calculate since timestamp
        since = datetime.now() - timedelta(days=days_back)
        
        # Fetch emails using adapter
        # The adapter already handles spam/trash filtering via Gmail API query
        emails = await self.adapter.fetch_emails(
            since=since,
            max_results=limit
        )
        
        return emails
    
    def group_by_thread(
        self,
        emails: List[StandardEmail]
    ) -> Dict[str, List[StandardEmail]]:
        """
        Group emails by thread_id for frontend consumption.
        
        This ensures the frontend receives organized thread objects
        instead of a flat list of emails.
        
        Args:
            emails: List of StandardEmail objects
            
        Returns:
            Dict mapping thread_id to list of emails in that thread
        """
        threads: Dict[str, List[StandardEmail]] = {}
        
        for email in emails:
            thread_id = email.thread_id
            
            if thread_id not in threads:
                threads[thread_id] = []
            
            threads[thread_id].append(email)
        
        # Sort emails within each thread by timestamp
        for thread_id in threads:
            threads[thread_id].sort(key=lambda e: e.timestamp)
        
        return threads
    
    async def fetch_and_group(
        self,
        limit: int = 10,
        days_back: int = 7
    ) -> Dict[str, List[StandardEmail]]:
        """
        Convenience method to fetch and group in one call.
        
        Args:
            limit: Maximum number of emails to fetch
            days_back: How many days back to fetch
            
        Returns:
            Dict of grouped threads
        """
        emails = await self.fetch_recent_emails(limit=limit, days_back=days_back)
        return self.group_by_thread(emails)
