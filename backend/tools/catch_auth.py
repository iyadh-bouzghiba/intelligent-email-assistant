import http.server
import socketserver
import urllib.parse
import os
import webbrowser
import json
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

load_dotenv()

# Configuration
PORT = 8000
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"]

# 1. Generate the URL
client_config = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}
try:
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

    print(f"\n🚀 --- ACTION REQUIRED ---")
    print(f"1. Open this URL in an **INCOGNITO/PRIVATE** window: \n{auth_url}")
    print(f"2. Log in as 'iyadh.bouzghiba.eng@gmail.com'.")
    print(f"3. The browser will redirect to localhost:8000. This script will CATCH the code automatically.")
    print(f"4. You can then close the browser tab.\n")

    # 2. Start a temporary server to catch the redirect
    class OAuthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            # Parse the code from the URL
            parsed_path = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed_path.query)
            
            if 'code' in query:
                code = query['code'][0]
                
                # Send a success message to the browser
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1 style='color:green;font-family:sans-serif'>SUCCESS!</h1><p>Code captured. You can close this tab.</p>")
                
                print(f"✅ Code Captured! Exchange in progress...")
                
                # 3. Immediately Exchange for Tokens
                try:
                    flow.fetch_token(code=code)
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
                    
                    print("✅ store.json created successfully.")
                    print("✨ Phase 1 COMPLETE.")
                    
                except Exception as e:
                    print(f"❌ Error during exchange: {e}")

                # Kill the server once done
                def kill_me():
                    raise KeyboardInterrupt
                kill_me()
                
            else:
                self.send_response(400)
                self.wfile.write(b"No code found in URL.")

    # Run the server
    print("📡 Listening for Google Redirect on port 8000...")
    # Allow address reuse to avoid 'Address already in use' errors
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", PORT), OAuthHandler) as httpd:
            httpd.handle_request() # Handle exactly ONE request
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Server error: {e}")

except Exception as e:
    print(f"Initialization error: {e}")
