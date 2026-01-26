import logging
import datetime
from typing import Optional, Dict, Any
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

from src.auth.credential_store import CredentialStore
from src.config import Config

logger = logging.getLogger(__name__)

class TokenManager:
    """
    Manages the lifecycle of OAuth tokens.
    Handles storage via CredentialStore and automatic refreshing of expired tokens.
    """
    
    def __init__(self, credential_store: CredentialStore):
        self.credential_store = credential_store

    def get_valid_credentials(self, user_id: str) -> Optional[Credentials]:
        """
        Retrieves valid `google.oauth2.credentials.Credentials` for a user.
        Automatically refreshes the token if it is expired.
        
        Args:
            user_id: The user ID to look up.
            
        Returns:
            Valid Credentials object if found/refreshed, else None.
            
        Raises:
             ValueError: If credentials exist but are invalid and cannot be refreshed.
        """
        creds_data = self.credential_store.get_credentials(user_id)
        if not creds_data:
            logger.warning(f"No credentials found for user {user_id}")
            return None
            
        try:
            creds = Credentials(**creds_data)
        except Exception as e:
            logger.error(f"Failed to instantiate Credentials for {user_id}: {e}")
            return None

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info(f"Token expired for user {user_id}, refreshing...")
                try:
                    creds.refresh(Request())
                    # Update storage with new token data
                    self._update_stored_credentials(user_id, creds)
                    logger.info(f"Token refreshed successfully for user {user_id}")
                except RefreshError as e:
                    logger.error(f"Failed to refresh token for user {user_id}: {e}")
                    # Optionally delete invalid credentials?
                    # self.credential_store.delete_credentials(user_id)
                    return None
                except Exception as e:
                     logger.error(f"Unexpected error refreshing token for {user_id}: {e}")
                     return None
            else:
                logger.warning(f"Credentials for {user_id} are invalid and cannot be refreshed.")
                return None
                
        return creds

    def _update_stored_credentials(self, user_id: str, creds: Credentials):
        """Helper to convert Credentials object back to dict and save."""
        creds_dict = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        # Filter out None values to keep dict clean if needed, though Credentials usually handles this
        # But we need to make sure we store what's needed for reconstruction
        self.credential_store.save_credentials(user_id, creds_dict)
