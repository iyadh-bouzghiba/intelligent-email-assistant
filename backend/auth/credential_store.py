from typing import Dict, Any, Optional
import logging
from backend.data.store import PersistenceManager
from backend.security.security_manager import encrypt_oauth_token, decrypt_oauth_token, SecurityManagerError

logger = logging.getLogger(__name__)

class CredentialStore:
    """
    Interface for storing and retrieving user credentials securely.
    Wraps the raw PersistenceManager to provide specific credential access methods.
    """
    
    def __init__(self, persistence_manager: PersistenceManager):
        self._pm = persistence_manager

    def save_credentials(self, user_id: str, credentials: Dict[str, Any]):
        """
        Saves credentials for a specific user with ENCRYPTION.

        SECURITY CONTRACT:
        - Encrypts 'token' and 'refresh_token' before storage
        - All other fields stored as-is (client_id, client_secret, etc.)
        - System halts if encryption fails (Security > Availability)

        Args:
            user_id: The unique identifier for the user.
            credentials: A dictionary containing OAuth credentials (token, refresh_token, etc.)

        Raises:
            SecurityManagerError: If encryption fails
        """
        # Load current state
        state = self._pm.load()
        tokens = state.get("tokens", {})

        # ENCRYPT sensitive tokens before storage
        encrypted_creds = credentials.copy()

        try:
            if 'token' in encrypted_creds and encrypted_creds['token']:
                encrypted_creds['token'] = encrypt_oauth_token(encrypted_creds['token'])
                logger.debug(f"[OK] [SECURITY] Encrypted access token for user {user_id}")

            if 'refresh_token' in encrypted_creds and encrypted_creds['refresh_token']:
                encrypted_creds['refresh_token'] = encrypt_oauth_token(encrypted_creds['refresh_token'])
                logger.debug(f"[OK] [SECURITY] Encrypted refresh token for user {user_id}")

        except SecurityManagerError as e:
            logger.critical(f"[FAIL] [SECURITY] Failed to encrypt tokens for user {user_id}: {e}")
            raise  # Fail fast - do not store unencrypted tokens

        # Update tokens with ENCRYPTED versions
        tokens[user_id] = encrypted_creds

        # Save back
        self._pm.save(
            tokens=tokens,
            watch_state=state.get("watch_state", {}),
            threads=state.get("threads", {})
        )

    def get_credentials(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves credentials for a specific user with DECRYPTION.

        SECURITY CONTRACT:
        - Decrypts 'token' and 'refresh_token' after retrieval
        - Returns plaintext tokens for immediate API use (in-memory only)
        - If decryption fails, returns None (token compromise/corruption)

        Args:
            user_id: The unique identifier for the user.

        Returns:
            Dict containing decrypted credentials or None if not found/invalid.
        """
        state = self._pm.load()
        encrypted_creds = state.get("tokens", {}).get(user_id)

        if not encrypted_creds:
            return None

        # DECRYPT sensitive tokens after retrieval
        decrypted_creds = encrypted_creds.copy()

        try:
            if 'token' in decrypted_creds and decrypted_creds['token']:
                decrypted_creds['token'] = decrypt_oauth_token(decrypted_creds['token'])
                logger.debug(f"[OK] [SECURITY] Decrypted access token for user {user_id}")

            if 'refresh_token' in decrypted_creds and decrypted_creds['refresh_token']:
                decrypted_creds['refresh_token'] = decrypt_oauth_token(decrypted_creds['refresh_token'])
                logger.debug(f"[OK] [SECURITY] Decrypted refresh token for user {user_id}")

        except SecurityManagerError as e:
            logger.error(f"[FAIL] [SECURITY] Failed to decrypt tokens for user {user_id}: {e}")
            logger.error(f"[FAIL] [SECURITY] Tokens may be corrupted or key changed. User must re-authenticate.")
            return None  # Token compromise or corruption - force re-auth

        return decrypted_creds

    def load_credentials(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Alias for get_credentials() - maintains backwards compatibility."""
        return self.get_credentials(user_id)

    def delete_credentials(self, user_id: str):
        """
        Removes credentials for a user (e.g. on logout).
        """
        state = self._pm.load()
        tokens = state.get("tokens", {})
        
        if user_id in tokens:
            del tokens[user_id]
            self._pm.save(
                tokens=tokens,
                watch_state=state.get("watch_state", {}),
                threads=state.get("threads", {})
            )
