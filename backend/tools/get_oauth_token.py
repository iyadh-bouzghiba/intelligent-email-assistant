import os
import sys
import json
import logging

# Ensure root (backend/) is in path
sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(os.getcwd()))

from google_auth_oauthlib.flow import InstalledAppFlow
from src.auth.credential_store import CredentialStore
from src.data.store import PersistenceManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify'
]

def main():
    print("=== MANUAL OAUTH TOKEN GENERATOR ===")
    
    secrets_file = "client_secrets.json"
    if not os.path.exists(secrets_file):
        print(f"❌ Error: {secrets_file} not found.")
        return

    try:
        # Create Flow
        flow = InstalledAppFlow.from_client_secrets_file(
            secrets_file, SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )

        # Generate URL
        auth_url, _ = flow.authorization_url(prompt='consent')

        print("\n👇 VISIT THIS URL TO AUTHORIZE 👇\n")
        print(auth_url)
        print("\n" + "="*50 + "\n")

        # Wait for code
        code = input("Enter the Authorization Code here: ").strip()

        if not code:
            print("❌ No code entered.")
            return

        # Fetch Token
        flow.fetch_token(code=code)
        creds = flow.credentials

        print("\n✅ Token fetched successfully!")
        
        # Save to Store
        pm = PersistenceManager()
        store = CredentialStore(pm)
        
        # We need a user ID. For manual bootstrap, we'll use "manual_user" or extract from token info if possible.
        # But CredentialStore doesn't parse ID token necessarily unless we request userinfo.email scope (which we removed).
        # So we'll use a hardcoded ID or the one from the existing store if any.
        
        # Let's see if we can get the email?
        # Without userinfo.email scope, we might not get the email address directly in some cases,
        # but usually the ID token has it if 'openid' is implicitly included or if we just use a placeholder.
        # Wait, the requirements said NO userinfo.email scope.
        # So we must use a placeholder ID unless we can get it from the profile later.
        
        user_id = "test_user" # As used in other parts of the system for single tenant
        
        # Construct dict for save_credentials expects
        # CredentialStore.save_credentials(user_id, credentials_object)
        
        store.save_credentials(user_id, creds)
        print(f"✅ Credentials saved to store.json for user: {user_id}")
        
        # Also Verify:
        print("Refresh Token Present:", bool(creds.refresh_token))

    except Exception as e:
        print(f"❌ Error during OAuth flow: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
