import http.server
import socketserver
import urllib.parse
import os
import json
import webbrowser
import sys
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

load_dotenv()

# --- 1. ID VERIFICATION ---
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
REDIRECT_URI = "http://localhost:8000/auth/google/callback"

print(f"\n🔍 --- SECURITY CHECK ---")
print(f"The Agent is using this Client ID from your .env file:")
print(f"👉 {CLIENT_ID}")
print(f"-------------------------------------------------------")
print(f"⚠️ ACTION REQUIRED: Go to Google Cloud Console -> Credentials.")
print(f"   Ensure the 'Client ID' there matches the one above EXACTLY.")
print(f"   If they are different, stop this script and update your .env file.")
print(f"-------------------------------------------------------\n")

# --- 2. PERSISTENT SERVER SETUP ---
PORT = 8000

class PersistentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return # Silence logs

    def do_GET(self):
        if self.path.startswith("/auth/google/callback"):
            parsed_path = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed_path.query)
            
            if 'code' in query:
                code = query['code'][0]
                self.server.auth_code = code
                
                # Success Page
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1 style='color:green;text-align:center'>SUCCESS! Code Captured. Return to Terminal.</h1>")
            elif 'error' in query:
                print(f"❌ Google returned an error: {query['error'][0]}")
                self.send_response(400)
                self.wfile.write(b"<h1 style='color:red'>Authorization Failed. Check Terminal.</h1>")
                self.server.auth_code = "ERROR"
            else:
                self.send_response(400)
        else:
            self.send_response(404)

def run_it():
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
        redirect_uri=REDIRECT_URI
    )
    
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

    print("🚀 Starting Local Server...")
    print(f"🔗 Opening: {auth_url}")
    webbrowser.open(auth_url)

    # Allow reuse address to prevent "Address already in use"
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), PersistentHandler) as httpd:
        httpd.auth_code = None
        print(f"📡 Listening on port {PORT}. Waiting for Google...")
        
        while httpd.auth_code is None:
            httpd.handle_request()
            
        if httpd.auth_code == "ERROR":
            print("❌ Authorization failed by Google.")
            return

        print("\n✅ Code Captured! Exchanging for Tokens...")
        try:
            flow.fetch_token(code=httpd.auth_code)
            creds = flow.credentials
            
            payload = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes),
            }
            
            os.makedirs("data", exist_ok=True)
            with open("data/store.json", "w") as f:
                json.dump(payload, f, indent=2)
            
            print("🎉 SUCCESS: store.json created.")
            # Verify Phase 1 completion
            import subprocess
            subprocess.run([sys.executable, "tests/validate_phase1_proof.py"])
            
        except Exception as e:
            print(f"❌ Token Exchange Error: {e}")

if __name__ == "__main__":
    try:
        run_it()
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
