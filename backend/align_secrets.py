import os
import json
from dotenv import load_dotenv

load_dotenv()

# Critical: Use 'web' type for Google Cloud Web Client IDs
client_config = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

with open("client_secrets.json", "w") as f:
    json.dump(client_config, f, indent=2)

print("✅ SUCCESS: client_secrets.json aligned with .env (web type).")
