"""
OAuth2 Token Refresh Service

Implements fault-tolerant token management with:
- Automatic token refresh before expiration
- Concurrency locking (prevents duplicate refresh calls)
- Encrypted token storage
- Graceful error handling
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from cryptography.fernet import Fernet
import redis
import json
from src.config import Config


class TokenRefreshService:
    """
    Service for managing OAuth2 token lifecycle.
    
    Features:
    - Automatic refresh before expiration
    - Refresh locking (prevents concurrent refreshes)
    - Encrypted storage
    - Error recovery
    """
    
    def __init__(self):
        """Initialize service with Redis for locking."""
        self.redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            decode_responses=False  # We need bytes for encryption
        )
        
        # Initialize encryption (use environment variable in production)
        encryption_key = Config.TOKEN_ENCRYPTION_KEY.encode() if hasattr(Config, 'TOKEN_ENCRYPTION_KEY') else Fernet.generate_key()
        self.cipher = Fernet(encryption_key)
    
    def encrypt_token(self, token_data: dict) -> bytes:
        """Encrypt token data for secure storage."""
        json_data = json.dumps(token_data)
        return self.cipher.encrypt(json_data.encode())
    
    def decrypt_token(self, encrypted_data: bytes) -> dict:
        """Decrypt token data from storage."""
        decrypted = self.cipher.decrypt(encrypted_data)
        return json.loads(decrypted.decode())
    
    def is_token_expired(self, credentials: Credentials) -> bool:
        """
        Check if token is expired or expiring soon.
        
        Args:
            credentials: Google OAuth2 credentials
            
        Returns:
            True if token is expired or expires within 5 minutes
        """
        if not credentials.expiry:
            return False
        
        # Refresh if expiring within 5 minutes
        buffer_time = timedelta(minutes=5)
        return datetime.utcnow() >= (credentials.expiry - buffer_time)
    
    async def get_valid_credentials(
        self,
        user_id: str,
        current_credentials: dict
    ) -> Credentials:
        """
        Get valid credentials, refreshing if necessary.
        
        This method implements refresh locking to prevent concurrent
        refresh calls when multiple requests come in simultaneously.
        
        Args:
            user_id: User identifier
            current_credentials: Current credential dict
            
        Returns:
            Valid Credentials object
        """
        # Create Credentials object
        creds = Credentials(
            token=current_credentials.get('token'),
            refresh_token=current_credentials.get('refresh_token'),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=Config.GOOGLE_CLIENT_ID,
            client_secret=Config.GOOGLE_CLIENT_SECRET,
            scopes=current_credentials.get('scopes', [])
        )
        
        # Check if token needs refresh
        if not self.is_token_expired(creds):
            return creds
        
        # Token needs refresh - acquire lock
        lock_key = f"token_refresh_lock:{user_id}"
        lock_acquired = self.redis_client.set(
            lock_key,
            "locked",
            nx=True,  # Only set if doesn't exist
            ex=30  # Expire after 30 seconds
        )
        
        if lock_acquired:
            # We got the lock - perform refresh
            try:
                print(f"[Token Refresh] Refreshing token for user {user_id}")
                creds.refresh(Request())
                
                # Store refreshed credentials
                refreshed_data = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'expiry': creds.expiry.isoformat() if creds.expiry else None,
                    'scopes': creds.scopes
                }
                
                # Encrypt and cache for other waiting requests
                encrypted = self.encrypt_token(refreshed_data)
                self.redis_client.setex(
                    f"refreshed_token:{user_id}",
                    60,  # Cache for 1 minute
                    encrypted
                )
                
                return creds
                
            finally:
                # Always release lock
                self.redis_client.delete(lock_key)
        
        else:
            # Another request is refreshing - wait for it
            print(f"[Token Refresh] Waiting for concurrent refresh for user {user_id}")
            
            for attempt in range(10):  # Wait up to 5 seconds
                await asyncio.sleep(0.5)
                
                # Check if refreshed token is available
                cached_token = self.redis_client.get(f"refreshed_token:{user_id}")
                if cached_token:
                    refreshed_data = self.decrypt_token(cached_token)
                    return Credentials(
                        token=refreshed_data['token'],
                        refresh_token=refreshed_data['refresh_token'],
                        token_uri='https://oauth2.googleapis.com/token',
                        client_id=Config.GOOGLE_CLIENT_ID,
                        client_secret=Config.GOOGLE_CLIENT_SECRET
                    )
            
            # Timeout - try refresh anyway
            print(f"[Token Refresh] Timeout waiting for concurrent refresh, attempting refresh")
            creds.refresh(Request())
            return creds
    
    async def refresh_if_needed(
        self,
        user_id: str,
        token_store: dict
    ) -> dict:
        """
        High-level method to refresh token if needed.
        
        Args:
            user_id: User identifier
            token_store: Current token store dict
            
        Returns:
            Updated token store dict
        """
        if user_id not in token_store:
            raise ValueError(f"No credentials found for user {user_id}")
        
        current_creds = token_store[user_id]
        valid_creds = await self.get_valid_credentials(user_id, current_creds)
        
        # Update token store with refreshed credentials
        token_store[user_id] = {
            'token': valid_creds.token,
            'refresh_token': valid_creds.refresh_token,
            'expiry': valid_creds.expiry.isoformat() if valid_creds.expiry else None,
            'scopes': valid_creds.scopes
        }
        
        return token_store


# Global token refresh service
token_refresh_service = TokenRefreshService()
