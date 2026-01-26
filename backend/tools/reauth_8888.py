import http.server, socketserver, urllib.parse, os, json, webbrowser
from google_auth_oauthlib.flow import Flow

# 1. CREDENTIALS
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
PORT = 8888
REDIRECT = f"http://localhost:{PORT}/auth/google/callback"

# Create temporary secrets for the flow
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
                self.wfile.write(b"<h1>Success! Auth Code Captured.</h1><p>Return to terminal Colonist.</p>")
        else: self.send_response(404); self.end_headers()

def run_reauth():
    print(f"📡 Initializing Re-Auth on Port {PORT}...")
    flow = Flow.from_client_secrets_file("client_secrets.json", 
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
        redirect_uri=REDIRECT)
    
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    print(f"\n🔒 PLEASE VISIT THIS URL TO RE-AUTHORIZE:\n\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Allow reuse address to prevent "Address already in use"
    socketserver.TCPServer.allow_reuse_address = True
    print(f"⏳ Waiting for callback on {REDIRECT}...")
    print("⚠️  IMPORTANT: Please stop the backend api.py if it is running on port 8888!")
    
    with socketserver.TCPServer(("", PORT), AuthHandler) as httpd:
        httpd.code = None
        while not httpd.code: httpd.handle_request()
        
        print(f"✅ Code Captured. Exchanging tokens...")
        flow.fetch_token(code=httpd.code)
        
        # Save to store.json
        os.makedirs("data", exist_ok=True)
        with open("data/store.json", "w") as f:
            creds = flow.credentials
            json.dump({
                "token": creds.token, 
                "refresh_token": creds.refresh_token, 
                "client_id": creds.client_id, 
                "client_secret": creds.client_secret
            }, f)
        
        print(f"🎉 store.json REGENERATED SUCCESSFULY.")
        print("🚀 You can now restart your backend api.py.")

if __name__ == "__main__": 
    run_reauth()
