from typing import Dict, Any, Optional
import logging
import os
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
        - Writes to Supabase first (production persistence)
        - Falls back to file storage (local dev only)
        - System halts if encryption fails (Security > Availability)

        Args:
            user_id: The unique identifier for the user.
            credentials: A dictionary containing OAuth credentials (token, refresh_token, etc.)

        Raises:
            SecurityManagerError: If encryption fails
        """
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

        # PRIMARY: Write to Supabase (production persistence)
        supabase_success = False
        try:
            from backend.infrastructure.supabase_store import SupabaseStore
            store = SupabaseStore()
            store.save_credential(
                provider="google",
                account_id=user_id,
                encrypted_payload=encrypted_creds,
                scopes=encrypted_creds.get('scopes', [])
            )
            supabase_success = True
            logger.info(f"[OK] [CREDENTIAL] Stored credentials to Supabase for user {user_id}")
        except Exception as e:
            logger.warning(f"[WARN] [CREDENTIAL] Supabase write failed for user {user_id}: {e}")

                # FALLBACK: Write to file (local dev backup)
        try:
            state = self._pm.load()
            tokens = state.get("tokens", {})
            tokens[user_id] = encrypted_creds
            self._pm.save(
                tokens=tokens,
                watch_state=state.get("watch_state", {}),
                threads=state.get("threads", {})
            )
            logger.debug(f"[OK] [CREDENTIAL] Wrote file backup for user {user_id}")
        except Exception as e:
            logger.warning(f"[WARN] [CREDENTIAL] File write failed for user {user_id}: {e}")


        # Require at least one successful write
        if not supabase_success:
            logger.error(f"[FAIL] [CREDENTIAL] No successful credential write for user {user_id}")
            # In production, this should fail hard. For now, log only.

    def get_credentials(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves credentials for a specific user with DECRYPTION.

        SECURITY CONTRACT:
        - Reads from Supabase first (production source of truth)
        - Falls back to file ONLY if ENV=local or ALLOW_FILE_CREDENTIALS=true
        - Decrypts 'token' and 'refresh_token' after retrieval
        - Returns plaintext tokens for immediate API use (in-memory only)
        - If decryption fails, returns None (token compromise/corruption)

        Args:
            user_id: The unique identifier for the user.

        Returns:
            Dict containing decrypted credentials or None if not found/invalid.
        """
        encrypted_creds = None
        source = None

        # PRIMARY: Read from Supabase
        try:
            from backend.infrastructure.supabase_store import SupabaseStore
            store = SupabaseStore()
            cred_data = store.get_credential(provider="google", account_id=user_id)
            if cred_data:
                encrypted_creds = cred_data["encrypted_payload"]
                source = "supabase"
                logger.info(f"[OK] [CREDENTIAL] Loaded credentials from Supabase for user {user_id}")
        except Exception as e:
            logger.warning(f"[WARN] [CREDENTIAL] Supabase read failed for user {user_id}: {e}")

        # FALLBACK: Read from file (dev only)
        if not encrypted_creds:
            env = os.getenv("ENVIRONMENT", "production").lower()
            allow_file = os.getenv("ALLOW_FILE_CREDENTIALS", "false").lower() == "true"

            if env == "local" or env == "development" or allow_file:
                try:
                    state = self._pm.load()
                    encrypted_creds = state.get("tokens", {}).get(user_id)
                    if encrypted_creds:
                        source = "file"
                        logger.info(f"[OK] [CREDENTIAL] Loaded credentials from file for user {user_id} (dev mode)")
                except Exception as e:
                    logger.warning(f"[WARN] [CREDENTIAL] File read failed for user {user_id}: {e}")
            else:
                logger.info(f"[INFO] [CREDENTIAL] File fallback disabled in {env} environment")

        if not encrypted_creds:
            logger.info(f"[INFO] [CREDENTIAL] No credentials found for user {user_id} (source: {source or 'none'})")
            return None

        # DECRYPT sensitive tokens after retrieval
        decrypted_creds = encrypted_creds.copy()

        try:
            if 'token' in decrypted_creds and decrypted_creds['token']:
                decrypted_creds['token'] = decrypt_oauth_token(decrypted_creds['token'])
                logger.debug(f"[OK] [SECURITY] Decrypted access token for user {user_id} from {source}")

            if 'refresh_token' in decrypted_creds and decrypted_creds['refresh_token']:
                decrypted_creds['refresh_token'] = decrypt_oauth_token(decrypted_creds['refresh_token'])
                logger.debug(f"[OK] [SECURITY] Decrypted refresh token for user {user_id} from {source}")

        except SecurityManagerError as e:
            logger.error(f"[FAIL] [SECURITY] Failed to decrypt tokens for user {user_id} from {source}: {e}")
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
        # PRIMARY: Delete from Supabase (source of truth)
        try:
            from backend.infrastructure.supabase_store import SupabaseStore
            store = SupabaseStore()
            store.delete_credential(provider="google", account_id=user_id)
            logger.info(f"[OK] [CREDENTIAL] Deleted credentials from Supabase for user {user_id}")
        except Exception as e:
            logger.warning(f"[WARN] [CREDENTIAL] Supabase delete failed for user {user_id}: {e}")

        # FALLBACK: Delete from file storage (dev backup)
        state = self._pm.load()
        tokens = state.get("tokens", {})

        if user_id in tokens:
            del tokens[user_id]
            self._pm.save(
                tokens=tokens,
                watch_state=state.get("watch_state", {}),
                threads=state.get("threads", {})
            )
            logger.debug(f"[OK] [CREDENTIAL] Deleted credentials from file for user {user_id}")
