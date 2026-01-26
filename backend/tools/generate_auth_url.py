import os
import sys
import logging
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

# Ensure root (backend/) is in path
sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(os.getcwd()))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Env
load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify'
]

def main():
    print("=== OAUTH URL GENERATOR (WEB FLOW) ===")
    
    secrets_file = "client_secrets.json"
    if not os.path.exists(secrets_file):
        print(f"❌ Error: {secrets_file} not found.")
        return

    redirect_uri = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/google/callback")
    
    try:
        # Create Flow
        flow = Flow.from_client_secrets_file(
            secrets_file, 
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )

        # Generate URL
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )

        print("\n👇 VISIT THIS URL TO AUTHORIZE 👇\n")
        print(auth_url)
        print("\n" + "="*50 + "\n")
        print(f"NOTE: After authorizing, you will be redirected to: {redirect_uri}")
        print("Copy the 'code' parameter from the URL bar of that page and provide it in the next step.")

    except Exception as e:
        print(f"❌ Error generating URL: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
