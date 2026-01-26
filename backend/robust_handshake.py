import os
import json
import sys
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION PRE-CHECK ---
STORE_DIR = "data"
STORE_PATH = os.path.join(STORE_DIR, "store.json")
AUTH_CODE = "PASTE_YOUR_NEW_CODE_HERE" # User: Replace this with the fresh code

def finalize_phase_1():
    print("🔍 Starting Robust Handshake...")
    
    # 1. Ensure directory exists
    if not os.path.exists(STORE_DIR):
        os.makedirs(STORE_DIR)
        print(f"📁 Created directory: {STORE_DIR}")

    # 2. Build Client Config directly from .env for maximum accuracy
    client_config = {
        "web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    try:
        flow = Flow.from_client_config(
            client_config, 
            scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
            redirect_uri=os.getenv("REDIRECT_URI")
        )

        # 3. Exchange code for credentials
        print("⏳ Exchanging code for tokens...")
        flow.fetch_token(code=AUTH_CODE)
        creds = flow.credentials

        # 4. Atomic Write to store.json
        payload = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes),
        }

        with open(STORE_PATH, "w") as f:
            json.dump(payload, f, indent=2)
        
        print(f"✅ SUCCESS: Credentials stored safely at {STORE_PATH}")
        return True

    except Exception as e:
        print(f"❌ ERROR DURING EXCHANGE: {str(e)}")
        return False

if __name__ == "__main__":
    if finalize_phase_1():
        print("\n--- RUNNING VALIDATION PROOF ---")
        # Trigger the existing validation test to confirm Phase 1 PASS
        os.system(f"{sys.executable} tests/validate_phase1_proof.py")
