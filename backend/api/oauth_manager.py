import google_auth_oauthlib.flow
from typing import Dict, Any, Optional

class OAuthManager:
    """
    Handles the OAuth2 flow for Google APIs.
    """
    def __init__(self, client_config: Dict[str, Any], redirect_uri: str):
        self.client_config = client_config
        self.redirect_uri = redirect_uri
        self.scopes = [
            'https://www.googleapis.com/auth/gmail.readonly'
        ]

    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generates the Google OAuth2 authorization URL.
        """
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            self.client_config,
            scopes=self.scopes
        )
        flow.redirect_uri = self.redirect_uri
        
        auth_kwargs = {
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        if state:
            auth_kwargs["state"] = state

        authorization_url, _ = flow.authorization_url(**auth_kwargs)
        return authorization_url

    def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchanges the authorization code for credentials (tokens).
        """
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            self.client_config,
            scopes=self.scopes
        )
        flow.redirect_uri = self.redirect_uri
        
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        return {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
            # Helper to get email if possible, though usually requires a separate call or id_token
            # We will handle email extraction in the service layer where this return is used.
        }
