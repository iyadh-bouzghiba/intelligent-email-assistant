import os
import json
from dotenv import load_dotenv
load_dotenv()

# Use the specific URI from your .env
redirect_uri = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/google/callback")
client_id = os.getenv("GOOGLE_CLIENT_ID")
client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
project_id = os.getenv("GCP_PROJECT_ID")

print(f"DEBUG: Redirect URI: {redirect_uri}")

data = {
    "web": {
        "client_id": client_id,
        "client_secret": client_secret,
        "project_id": project_id,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "redirect_uris": [redirect_uri]
    }
}

with open("client_secrets.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"✅ client_secrets.json updated with redirect_uri: {redirect_uri}")
