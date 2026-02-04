"""
SECURITY MANAGER — OAuth Token Encryption & Secrets Governance

ZERO-TRUST PRINCIPLE:
- All OAuth tokens (access + refresh) are encrypted at rest
- Decryption happens only in-memory at API call time
- No plaintext tokens in logs, databases, or persistent storage
- System halts if encryption environment is invalid

FAILURE MODE:
Security > Availability
If encryption fails, the system MUST refuse to start.
"""

import os
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

# Configure logging with secret redaction
logger = logging.getLogger(__name__)


class SecurityManagerError(Exception):
    """Raised when security manager encounters a fatal error"""
    pass


class SecurityManager:
    """
    Cryptographic vault for OAuth token encryption using Fernet symmetric encryption.

    Responsibilities:
    - Load and validate FERNET_KEY from environment
    - Encrypt OAuth tokens before Supabase storage
    - Decrypt OAuth tokens at service layer call time
    - Enforce zero-trust security contract
    """

    def __init__(self):
        """
        Initialize SecurityManager and load encryption key.

        Raises:
            SecurityManagerError: If FERNET_KEY is missing or invalid
        """
        self._cipher: Optional[Fernet] = None
        self._key_loaded = False

        # Immediately validate environment on initialization
        self.load_or_fail_key()

    def load_or_fail_key(self) -> None:
        """
        Load FERNET_KEY from environment and initialize Fernet cipher.

        CRITICAL: This method enforces the security contract.
        If the key is missing, malformed, or invalid, the system MUST NOT start.

        Raises:
            SecurityManagerError: If key is missing or invalid
        """
        key = os.getenv("FERNET_KEY")

        if not key:
            logger.critical("[FAIL] [SECURITY] FERNET_KEY environment variable is MISSING")
            logger.critical("[FAIL] [SECURITY] Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
            raise SecurityManagerError(
                "FERNET_KEY is required but not set. System cannot start without encryption."
            )

        if not key.strip():
            logger.critical("[FAIL] [SECURITY] FERNET_KEY is empty")
            raise SecurityManagerError("FERNET_KEY cannot be empty")

        # Validate key format by attempting to initialize Fernet
        try:
            # Fernet keys must be 32 url-safe base64-encoded bytes
            self._cipher = Fernet(key.encode())
            self._key_loaded = True
            logger.info("[OK] [SECURITY] Encryption key loaded successfully")
        except Exception as e:
            logger.critical(f"[FAIL] [SECURITY] FERNET_KEY is INVALID: {type(e).__name__}")
            logger.critical("[FAIL] [SECURITY] Key must be a valid Fernet key (32 url-safe base64-encoded bytes)")
            raise SecurityManagerError(
                f"FERNET_KEY is malformed or invalid: {type(e).__name__}"
            ) from e

    def encrypt_token(self, token: str) -> str:
        """
        Encrypt an OAuth token using Fernet symmetric encryption.

        Args:
            token: The plaintext OAuth token (access or refresh)

        Returns:
            Base64-encoded encrypted token (safe for database storage)

        Raises:
            SecurityManagerError: If encryption fails or cipher is not initialized
        """
        if not self._key_loaded or self._cipher is None:
            logger.critical("[FAIL] [SECURITY] Attempted to encrypt token with uninitialized cipher")
            raise SecurityManagerError("Cipher not initialized. Cannot encrypt tokens.")

        if not token or not token.strip():
            raise SecurityManagerError("Cannot encrypt empty token")

        try:
            # Encrypt and return as string (Fernet returns bytes)
            encrypted_bytes = self._cipher.encrypt(token.encode())
            encrypted_token = encrypted_bytes.decode()

            # Log successful encryption WITHOUT logging the token
            logger.debug("[OK] [SECURITY] Token encrypted successfully")
            return encrypted_token

        except Exception as e:
            logger.error(f"[FAIL] [SECURITY] Token encryption failed: {type(e).__name__}")
            raise SecurityManagerError(f"Failed to encrypt token: {type(e).__name__}") from e

    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt an OAuth token at API call time (in-memory only).

        SECURITY CONTRACT:
        - Decryption happens ONLY at service layer boundary
        - Plaintext token exists ONLY in memory during API call
        - Never persist decrypted tokens

        Args:
            encrypted_token: Base64-encoded encrypted token from database

        Returns:
            Plaintext OAuth token for immediate API use

        Raises:
            SecurityManagerError: If decryption fails or token is invalid
        """
        if not self._key_loaded or self._cipher is None:
            logger.critical("[FAIL] [SECURITY] Attempted to decrypt token with uninitialized cipher")
            raise SecurityManagerError("Cipher not initialized. Cannot decrypt tokens.")

        if not encrypted_token or not encrypted_token.strip():
            raise SecurityManagerError("Cannot decrypt empty token")

        try:
            # Decrypt and return as string
            decrypted_bytes = self._cipher.decrypt(encrypted_token.encode())
            plaintext_token = decrypted_bytes.decode()

            # Log successful decryption WITHOUT logging the token
            logger.debug("[OK] [SECURITY] Token decrypted successfully")
            return plaintext_token

        except InvalidToken as e:
            logger.error("[FAIL] [SECURITY] Token decryption failed: Invalid or corrupted token")
            raise SecurityManagerError("Token is invalid or corrupted. Decryption failed.") from e
        except Exception as e:
            logger.error(f"[FAIL] [SECURITY] Token decryption failed: {type(e).__name__}")
            raise SecurityManagerError(f"Failed to decrypt token: {type(e).__name__}") from e

    def validate_environment(self) -> dict:
        """
        Validate the security environment and return a status report.

        Returns:
            dict: Security environment status with keys:
                - fernet_key_loaded: bool
                - cipher_initialized: bool
                - status: "GREEN" | "RED"
                - message: str
        """
        is_valid = self._key_loaded and self._cipher is not None

        return {
            "fernet_key_loaded": self._key_loaded,
            "cipher_initialized": self._cipher is not None,
            "status": "GREEN" if is_valid else "RED",
            "message": "Encryption environment is valid" if is_valid else "Encryption environment is INVALID"
        }

    def __repr__(self) -> str:
        """Safe string representation (never exposes key material)"""
        status = "INITIALIZED" if self._key_loaded else "UNINITIALIZED"
        return f"<SecurityManager status={status}>"


# Singleton instance for application-wide use
_security_manager_instance: Optional[SecurityManager] = None


def get_security_manager() -> SecurityManager:
    """
    Get or create the singleton SecurityManager instance.

    This ensures only one encryption key is loaded per application lifecycle.

    Returns:
        SecurityManager: The singleton instance

    Raises:
        SecurityManagerError: If initialization fails
    """
    global _security_manager_instance

    if _security_manager_instance is None:
        logger.info("🔐 [SECURITY] Initializing SecurityManager singleton...")
        _security_manager_instance = SecurityManager()

    return _security_manager_instance


# Convenience functions for application code
def encrypt_oauth_token(token: str) -> str:
    """Encrypt an OAuth token using the singleton SecurityManager"""
    return get_security_manager().encrypt_token(token)


def decrypt_oauth_token(encrypted_token: str) -> str:
    """Decrypt an OAuth token using the singleton SecurityManager"""
    return get_security_manager().decrypt_token(encrypted_token)


def validate_security_environment() -> dict:
    """Validate the security environment using the singleton SecurityManager"""
    return get_security_manager().validate_environment()
