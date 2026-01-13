from src.main import EmailAssistant
from fastapi import FastAPI
from typing import Dict, Any
from fastapi.responses import RedirectResponse
from fastapi import Request
from fastapi import HTTPException
from src.api.models import SummaryResponse
from src.api.gmail_client import GmailClient
from src.api.oauth_manager import OAuthManager
import os

app = FastAPI(title="Secure Email Assistant API")

# Mock storage for user tokens
# In production, use an encrypted database
USER_TOKEN_STORE: Dict[str, Any] = {}

# Google OAuth Config (Should be in env vars)
CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8000/auth/google/callback")

oauth_manager = OAuthManager(CLIENT_CONFIG, REDIRECT_URI)
assistant = EmailAssistant()

@app.get("/auth/google/login")
async def login_google():
    """Starts the OAuth flow."""
    auth_url = oauth_manager.get_authorization_url()
    return RedirectResponse(auth_url)

@app.get("/auth/google/callback")
async def callback_google(code: str, request: Request):
    """Handles the redirect from Google with the auth code."""
    try:
        tokens = oauth_manager.exchange_code_for_tokens(code)
        # Use a real user identifier here (e.g., from a session cookie)
        user_id = "test_user" 
        USER_TOKEN_STORE[user_id] = tokens
        return {"status": "authenticated", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/emails/{email_id}/summary", response_model=SummaryResponse)
async def get_summary(email_id: str):
    """Securely fetches and summarizes an email."""
    user_id = "test_user" # Simulated user context
    if user_id not in USER_TOKEN_STORE:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        client = GmailClient(USER_TOKEN_STORE[user_id])
        raw_email = client.get_email_by_id(email_id)
        
        # Parse Gmail message to dict for our assistant
        email_data = {
            "id": raw_email['id'],
            "thread_id": raw_email['threadId'],
            "subject": next((h['value'] for h in raw_email['payload']['headers'] if h['name'] == 'Subject'), "No Subject"),
            "sender": next((h['value'] for h in raw_email['payload']['headers'] if h['name'] == 'From'), "Unknown"),
            "body": client.parse_body(raw_email),
            "is_html": False # parse_body returns text
        }
        
        analysis = assistant.process_incoming_email(email_data)
        return analysis.summary # returns the ThreadSummary object (mapped to SummaryResponse)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
