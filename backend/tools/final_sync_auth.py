import http.server, socketserver, urllib.parse, os, json, webbrowser
from google_auth_oauthlib.flow import Flow

# 1. FORCE SYNC FILES
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT = "http://localhost:8000/auth/google/callback"

# Update client_secrets.json
secrets_data = {"web": {"client_id": CLIENT_ID, "client_secret": SECRET, 
                "auth_uri": "https://accounts.google.com/o/oauth2/auth", 
                "token_uri": "https://oauth2.googleapis.com/token"}}
with open("client_secrets.json", "w") as f:
    json.dump(secrets_data, f)

# 2. PERSISTENT SERVER
class AuthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if "/auth/google/callback" in self.path:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if 'code' in query:
                self.server.code = query['code'][0]
                self.send_response(200); self.end_headers()
                self.wfile.write(b"<h1>Success! Return to terminal Colonist.</h1>")
        else: self.send_response(404); self.end_headers()

def run():
    flow = Flow.from_client_secrets_file("client_secrets.json", 
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
        redirect_uri=REDIRECT)
    
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    # --- VERIFICATION START ---
    print("\n🔍 VERIFICATION: Checking Client IDs AND Secrets on disk...")
    # 1. Read client_secrets.json
    with open("client_secrets.json", "r") as f:
        data = json.load(f)["web"]
        cid_file = data["client_id"]
        sec_file = data["client_secret"]
    
    # 2. Read .env
    cid_env = "NOT_FOUND"
    sec_env = "NOT_FOUND"
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("GOOGLE_CLIENT_ID="):
                    cid_env = line.strip().split("=")[1]
                if line.startswith("GOOGLE_CLIENT_SECRET="):
                    sec_env = line.strip().split("=")[1]
    
    print(f"   client_secrets.json -> ID: {cid_file[:5]}... | Secret: {sec_file[:5]}...")
    print(f"   .env                -> ID: {cid_env[:5]}... | Secret: {sec_env[:5]}...")
    
    if cid_file == cid_env and sec_file == sec_env:
        print("✅ ALL CREDENTIALS MATCH. Launching process...\n")
    else:
        print("❌ MISMATCH DETECTED! Check files.\n")
    # --- VERIFICATION END ---

    print(f"\n🚀 AUTH URL: {auth_url}\n")
    webbrowser.open(auth_url)

    # Allow reuse address to prevent "Address already in use"
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", 8000), AuthHandler) as httpd:
        httpd.code = None
        while not httpd.code: httpd.handle_request()
        
        print(f"✅ Code Captured. Exchanging...")
        flow.fetch_token(code=httpd.code)
        
        # Save to store.json
        os.makedirs("data", exist_ok=True)
        with open("data/store.json", "w") as f:
            creds = flow.credentials
            json.dump({"token": creds.token, "refresh_token": creds.refresh_token, 
                       "client_id": creds.client_id, "client_secret": creds.client_secret}, f)
        print("🎉 store.json SAVED. Phase 1 Complete.")

if __name__ == "__main__": run()
