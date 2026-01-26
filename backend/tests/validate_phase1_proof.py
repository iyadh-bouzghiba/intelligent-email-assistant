
"""
PHASE 1 — HARD PROOF VALIDATION SCRIPT
CRITICAL: This script must use REAL code paths and REAL OAuth credentials.
NO MOCKS. NO ASSUMPTIONS.
"""

import sys
import traceback
import os

# Adjust path so src/ is importable when running from backend/
# We need to make sure we're in backend/
current_dir = os.getcwd()
if 'backend' not in current_dir and os.path.exists('backend'):
    sys.path.append('backend')
else:
    sys.path.append(".")

from google.auth.exceptions import GoogleAuthError
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# --- IMPORT REAL INTEGRATION CODE ---
try:
    from src.integrations.gmail import GmailClient
    from src.auth.credential_store import CredentialStore
    from src.data.store import PersistenceManager
    from src.config import Config
except ImportError as e:
    print(f"[FATAL] Failed to import real codebase: {e}")
    sys.exit(1)

def main():
    print("\n=== PHASE 1 HARD PROOF VALIDATION START ===\n")

    try:
        print("[STEP 1] Loading stored OAuth credentials...")
        
        # Load via Real PersistenceManager & CredentialStore
        pm = PersistenceManager()
        store = CredentialStore(pm)
        
        # Attempt to find a valid user (assuming single tenant or 'test_user')
        state = pm.load()
        tokens = state.get("tokens", {})
        
        if not tokens:
            raise ValueError("NO TOKENS FOUND IN STORE. CANNOT PROCEED.")
            
        # Pick the first available user
        user_id = list(tokens.keys())[0]
        creds_data = store.get_credentials(user_id)
        
        if not creds_data:
             raise ValueError(f"Failed to retrieve credentials for user {user_id}")

        print(f"USER_ID: {user_id}")
        print("HAS_REFRESH_TOKEN:", bool(creds_data.get('refresh_token')))
        print("SCOPES:", creds_data.get('scopes'))

        print("\n[STEP 2] Creating Gmail service client...")
        # Use REAL GmailClient
        client = GmailClient(creds_data)
        service = client.service

        print("\n[STEP 3] Executing users().getProfile()...")
        profile = service.users().getProfile(userId="me").execute()
        print("PROFILE RESPONSE:", profile)

        print("\n[STEP 4] Registering Gmail WATCH...")
        
        # Resolve Project ID
        project_id = Config.GCP_PROJECT_ID
        if not project_id:
            # Try to guess or fail?
            # User script had specific format.
            project_id = "<UNKNOWN_PROJECT>"
            
        topic_name = f"projects/{project_id}/topics/gmail-events"
        print(f"Target Topic: {topic_name}")

        watch_response = service.users().watch(
            userId="me",
            body={
                "topicName": topic_name,
                "labelIds": ["INBOX"]
            }
        ).execute()

        print("WATCH RAW RESPONSE:", watch_response)

        print("\n=== PHASE 1 HARD PROOF VALIDATION COMPLETE ===\n")

    except GoogleAuthError as auth_err:
        print("\n[AUTH ERROR CAUGHT]")
        print(type(auth_err).__name__)
        print(str(auth_err))
        traceback.print_exc()

    except Exception as e:
        print("\n[UNEXPECTED ERROR CAUGHT]")
        print(type(e).__name__)
        print(str(e))
        traceback.print_exc()


if __name__ == "__main__":
    main()
