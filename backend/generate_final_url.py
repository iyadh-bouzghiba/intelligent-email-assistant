import os
import json
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

load_dotenv()

# Ensure client_secrets.json is read as a 'web' application type
with open("client_secrets.json", "r") as f:
    client_config = json.load(f)

flow = Flow.from_client_config(
    client_config,
    scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"],
    redirect_uri=os.getenv("REDIRECT_URI")
)

auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

print("\n--- FINAL AUTHORIZATION URL ---")
print(auth_url)
with open("final_auth_url.txt", "w") as f:
    f.write(auth_url)
print("\n--- INSTRUCTIONS ---")
print("1. Click the URL.")
print("2. If a warning appears, click 'Advanced' -> 'Go to Email Summarization Assistant (unsafe)'.")
print("3. Authorize access.")
print("4. Copy the code from the address bar (the text after 'code=') and paste it here.")
