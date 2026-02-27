import google_auth_oauthlib.flow
from typing import Dict, Any, Optional
import hashlib
import base64
import secrets

class OAuthManager:
    """
    Handles the OAuth2 flow for Google APIs with PKCE support.

    CRITICAL FIX: Implements PKCE (Proof Key for Code Exchange) to prevent
    "invalid_grant: Missing code verifier" errors from Google OAuth.
    """
    def __init__(self, client_config: Dict[str, Any], redirect_uri: str):
        self.client_config = client_config
        self.redirect_uri = redirect_uri
        self.scopes = [
            'openid',  # CRITICAL: Explicitly request to prevent scope mismatch
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ]
        # PKCE code_verifier storage (temporary, per-instance)
        self._code_verifier = None

    def _generate_code_verifier(self) -> str:
        """
        Generate a cryptographically random code_verifier for PKCE.
        Per RFC 7636: 43-128 characters from [A-Z][a-z][0-9]-._~
        """
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8')
        # Remove padding
        return code_verifier.rstrip('=')

    def _generate_code_challenge(self, code_verifier: str) -> str:
        """
        Generate code_challenge from code_verifier using SHA256.
        Per RFC 7636: BASE64URL(SHA256(ASCII(code_verifier)))
        """
        digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode('utf-8')
        return code_challenge.rstrip('=')

    def get_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        """
        Generates the Google OAuth2 authorization URL with PKCE.

        Returns:
            tuple: (authorization_url, code_verifier) - MUST store code_verifier for callback
        """
        # Generate PKCE parameters
        self._code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(self._code_verifier)

        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            self.client_config,
            scopes=self.scopes
        )
        flow.redirect_uri = self.redirect_uri

        # CRITICAL: Add PKCE parameters to authorization request
        auth_kwargs = {
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "select_account consent",  # CRITICAL: Force account picker + consent screen
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"  # SHA256 hashing
        }
        if state:
            auth_kwargs["state"] = state

        authorization_url, _ = flow.authorization_url(**auth_kwargs)

        # Return both URL and code_verifier (caller must store code_verifier)
        return authorization_url, self._code_verifier

    def exchange_code_for_tokens(self, code: str, code_verifier: str) -> Dict[str, Any]:
        """
        Exchanges the authorization code for credentials (tokens) using PKCE.

        Args:
            code: Authorization code from Google callback
            code_verifier: The code_verifier generated during authorization (REQUIRED for PKCE)
        """
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            self.client_config,
            scopes=self.scopes
        )
        flow.redirect_uri = self.redirect_uri

        # CRITICAL: Include code_verifier in token exchange request
        flow.fetch_token(code=code, code_verifier=code_verifier)
        creds = flow.credentials

        result = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
        }

        # Include id_token if present (contains user email in JWT claims)
        if hasattr(creds, 'id_token') and creds.id_token:
            result['id_token'] = creds.id_token

        return result
