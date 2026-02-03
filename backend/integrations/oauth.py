import os
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from typing import Dict, Any

# Environment variables should be used in production
# GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
# GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

# Configurable scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class OAuthManager:
    """Handles the OAuth 2.0 flow for Google APIs."""
    
    def __init__(self, client_config: Dict[str, Any], redirect_uri: str):
        self.client_config = client_config
        self.redirect_uri = redirect_uri

    def get_authorization_url(self) -> str:
        """Generates the Google OAuth login URL."""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=SCOPES,
            redirect_uri=self.redirect_uri
        )
        # access_type='offline' is critical for getting a refresh_token
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        return authorization_url

    def exchange_code_for_tokens(self, auth_code: str) -> Dict[str, Any]:
        """Exchanges an authorization code for access and refresh tokens."""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=SCOPES,
            redirect_uri=self.redirect_uri
        )
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials
        
        return {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes
        }
