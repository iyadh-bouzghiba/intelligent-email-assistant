import os
import json
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

load_dotenv()

# Verify client_secrets.json exists
if not os.path.exists("client_secrets.json"):
    print("Error: client_secrets.json not found. Run align_secrets.py first.")
    exit(1)

with open("client_secrets.json", "r") as f:
    client_config = json.load(f)

# Ensure redirect_uri is set
redirect_uri = os.getenv("REDIRECT_URI")
if not redirect_uri:
    print("Error: REDIRECT_URI not found in environment variables.")
    exit(1)

flow = Flow.from_client_config(
    client_config,
    scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
    redirect_uri=redirect_uri
)

auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

print("\n!!! USER ACTION REQUIRED !!!")
print(f"URL: {auth_url}")
with open("auth_url.txt", "w") as f:
    f.write(auth_url)
print("\nInstructions: 1. Visit URL. 2. Login. 3. Copy the 'code' from the browser address bar.")
