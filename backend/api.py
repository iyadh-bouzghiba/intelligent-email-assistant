import os
import sys
import json
import uvicorn
from pathlib import Path
from dateutil import parser
import datetime

# --- STEP 1: DYNAMIC DEPENDENCY INJECTOR ---
# This ensures Python finds your libraries (Anaconda/Windows) without hardcoding paths
import site
for path in site.getsitepackages():
    if path not in sys.path:
        sys.path.append(path)

# --- STEP 2: DIAGNOSTIC & HEALTH CHECK ---
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def log_system(msg):
    print(f"🧠 [Executive Brain] {msg}")

log_system("Initializing Intelligence Layer...")
log_system(f"Python: {sys.executable}")
log_system(f"Root: {os.getcwd()}")

# --- STEP 3: IMPORTS ---
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from services.gmail_engine import run_engine
from services.summarizer import Summarizer
from dotenv import load_dotenv

load_dotenv()

# --- STEP 4: BULLETPROOF PATH ENFORCEMENT ---
BASE_DIR = Path(__file__).parent.absolute()
CLIENT_SECRETS_PATH = BASE_DIR / "client_secrets.json"

# Task 1: Absolute Pathing - No Relative Paths
CREDENTIALS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'credentials'))
log_system(f"Credentials Vault (Absolute): {CREDENTIALS_DIR}")

# Task 1: Self-Healing Vault Creation
os.makedirs(CREDENTIALS_DIR, exist_ok=True)

app = FastAPI(title="Executive Email Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Brain
try:
    brain = Summarizer()
    log_system("✅ AI Brain initialized successfully")
except Exception as e:
    log_system(f"⚠️ Warning: AI Brain initialization issue: {e}")
    brain = None

# OAuth Config
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "http://127.0.0.1:8888").rstrip("/")
REDIRECT_URI = f"{PRODUCTION_URL}/auth/google/callback"
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")

@app.get("/health")
async def health_check():
    return {"status": "ok", "vault": CREDENTIALS_DIR}

@app.get("/api/health")
async def api_health_check():
    return {"status": "online", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}

@app.get("/api/accounts")
async def list_accounts():
    """
    Scans the credentials directory and returns a list of connected email addresses.
    """
    try:
        if not os.path.exists(CREDENTIALS_DIR):
            return {"accounts": []}
        
        # Look for files ending with _token.json
        files = [f for f in os.listdir(CREDENTIALS_DIR) if f.endswith("_token.json")]
        emails = [f.replace("_token.json", "") for f in files]
        
        # Also include legacy main_account if it exists, for backward compatibility
        if os.path.exists(os.path.join(CREDENTIALS_DIR, "main_account.json")):
             if "main_account" not in emails:
                 emails.append("main_account")
                 
        return {"accounts": emails}
    except Exception as e:
        log_system(f"❌ Failed to list accounts: {e}")
        return {"accounts": [], "error": str(e)}

@app.get("/auth/google/login")
async def google_login():
    print("🔑 [OAuth] Starting login flow...")
    if not CLIENT_SECRETS_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Missing {CLIENT_SECRETS_PATH}")
        
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS_PATH),
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt='consent select_account', access_type='offline')
    return RedirectResponse(auth_url)

@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str):
    print("📩 [OAuth] Callback received. Exchanging code...")
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS_PATH),
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
    )
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(authorization_response=str(request.url))
    creds = flow.credentials

    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    
    # Get user email to use as filename
    creds_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "token_uri": "https://oauth2.googleapis.com/token"
    }
    
    temp_creds = Credentials(
        token=creds.token,
        refresh_token=creds.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds.client_id,
        client_secret=creds.client_secret
    )
    service = build('gmail', 'v1', credentials=temp_creds)
    profile = service.users().getProfile(userId='me').execute()
    email = profile['emailAddress']
    
    file_path = os.path.join(CREDENTIALS_DIR, f"{email}_token.json")
    with open(file_path, 'w') as f:
        json.dump(creds_data, f, indent=2)
    
    print(f"✅ [OAuth] Credentials saved for {email} to {file_path}")
    return RedirectResponse(FRONTEND_URL)

@app.get("/api/briefing")
async def get_briefing(email: str = None):
    """
    UNBREAKABLE ENDPOINT - Guaranteed 200 OK Response
    Returns briefings or empty list with error details
    """
    # Task 1: Global Catch-All - Wrap EVERYTHING
    try:
        # Task 1: Clean Initialization
        all_briefings = []
        seen_emails = set()
        
        # Targeted Filter or Global Feed?
        if email:
            credential_files = [f"{email}_token.json"]
            log_system(f"🎯 Targeted sync for: {email}")
        else:
            log_system("🔄 Aggregating multi-account briefings (UNBREAKABLE MODE)...")
            
            # Bulletproof Directory Check
            if not os.path.exists(CREDENTIALS_DIR):
                os.makedirs(CREDENTIALS_DIR, exist_ok=True)
                log_system("⚠️ Vault directory created. No accounts connected.")
                return {"account": "No Accounts", "briefings": [], "status": "empty_vault"}

            try:
                credential_files = [f for f in os.listdir(CREDENTIALS_DIR) if f.endswith("_token.json")]
            except Exception as e:
                log_system(f"❌ Failed to read vault directory: {e}")
                return {"account": "Error", "briefings": [], "status": "vault_read_error", "error": str(e)}
        
        if not credential_files:
            log_system("⚠️ Vault is empty. No accounts connected yet.")
            return {"account": "No Accounts", "briefings": [], "status": "no_credentials"}

        log_system(f"📂 Found {len(credential_files)} credential file(s): {credential_files}")

        # Process each credential file
        for filename in credential_files:
            try:
                cred_path = os.path.join(CREDENTIALS_DIR, filename)
                account_email = filename.replace("_token.json", "")
                
                # Safe JSON Loading
                log_system(f"🔐 Loading credentials for: {account_email}")
                try:
                    with open(cred_path, 'r') as f:
                        token_data = json.load(f)
                except (json.JSONDecodeError, IOError, FileNotFoundError) as e:
                    log_system(f"⚠️ Skipping malformed vault file: {filename} - {str(e)}")
                    continue

                # Token Verification & Migration Compatibility
                if 'token_uri' not in token_data:
                    log_system(f"⚠️ Adding missing token_uri to {account_email}")
                    token_data['token_uri'] = "https://oauth2.googleapis.com/token"
                
                if 'client_id' not in token_data or 'client_secret' not in token_data:
                    log_system(f"❌ Missing client_id/secret in {filename}, skipping")
                    continue
                
                if 'token' not in token_data:
                    log_system(f"❌ Missing token in {filename}, skipping")
                    continue

                # Safe Gmail Fetch
                try:
                    emails = run_engine(token_data)
                    if not emails:
                        log_system(f"📭 No emails fetched for {account_email}")
                        continue
                    log_system(f"📧 Fetched {len(emails)} emails for {account_email}")
                except Exception as e:
                    log_system(f"⚠️ Failed to fetch emails for {account_email}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue

                # Process each email
                for email in emails:
                    try:
                        # Field Validation
                        subject = email.get('subject', 'No Subject')
                        sender = email.get('sender', 'Unknown Sender')
                        date = email.get('date', datetime.datetime.now(datetime.timezone.utc).isoformat())
                        body = email.get('body', '')
                        
                        # Deduplication
                        email_signature = f"{subject}:{date}:{account_email}"
                        if email_signature in seen_emails:
                            continue
                        seen_emails.add(email_signature)
                        
                        # AI Summarization
                        if brain:
                            try:
                                summary_raw = brain.summarize(email)
                            except Exception as e:
                                log_system(f"⚠️ Brain failed, using fallback: {str(e)}")
                                summary_raw = body[:200]
                        else:
                            summary_raw = body[:200]
                        
                        # Smart Parsing
                        summary_text = summary_raw
                        action_text = "None"
                        priority = "Medium"
                        category = "General"
                        
                        for line in summary_raw.split('\n'):
                            if line.startswith("SUMMARY:"):
                                summary_text = line.replace("SUMMARY:", "").strip()
                            elif line.startswith("ACTION:"):
                                action_text = line.replace("ACTION:", "").strip()
                            elif line.startswith("PRIORITY:"):
                                priority_val = line.replace("PRIORITY:", "").strip()
                                if priority_val in ["Low", "Medium", "High"]:
                                    priority = priority_val
                            elif line.startswith("CATEGORY:"):
                                cat_val = line.replace("CATEGORY:", "").strip()
                                if cat_val in ["Security", "Financial", "General"]:
                                    category = cat_val

                        briefing = {
                            "account": account_email,
                            "subject": subject,
                            "sender": sender,
                            "priority": priority,
                            "category": category,
                            "should_alert": category == "Security" and priority == "High",
                            "summary": summary_text or "No summary available",
                            "action": action_text,
                            "date": date
                        }
                        all_briefings.append(briefing)
                        
                    except Exception as e:
                        log_system(f"⚠️ Failed to process email in {account_email}: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                log_system(f"✅ [LOG] Successfully loaded account: {account_email}")
                        
            except Exception as e:
                log_system(f"❌ Unexpected error for {filename}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue

        # Safe Sorting
        def sort_key(b):
            try:
                return parser.parse(b.get('date', ''))
            except Exception:
                return datetime.datetime.now(datetime.timezone.utc)

        try:
            all_briefings.sort(key=sort_key, reverse=True)
        except Exception as e:
            log_system(f"⚠️ Sorting failed, returning unsorted: {e}")
        
        log_system(f"✅ Returning {len(all_briefings)} total briefings (deduplicated)")
        return {"account": "Multi-Account Feed", "briefings": all_briefings[:10], "status": "success"}
        
    except Exception as e:
        # FINAL FAIL-SAFE - ALWAYS RETURN 200 OK
        log_system(f"🚨 CRITICAL FAILURE: {str(e)}")
        log_system("=" * 80)
        log_system("FULL TRACEBACK:")
        import traceback
        traceback.print_exc()
        log_system("=" * 80)
        
        return {
            "account": "Error",
            "briefings": [],
            "status": "partial_failure",
            "error": str(e)
        }

if __name__ == "__main__":
    log_system("BACKEND STABILIZED ON PORT 8888")
    uvicorn.run("api:app", host="127.0.0.1", port=8888, reload=True)
