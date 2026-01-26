import os, json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def fetch_test():
    # 1. Load the tokens we just captured
    with open('data/store.json', 'r') as f:
        data = json.load(f)
    
    creds = Credentials(
        token=data['token'],
        refresh_token=data.get('refresh_token'),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=data['client_id'],
        client_secret=data['client_secret']
    )

    # 2. Build the Gmail Service
    service = build('gmail', 'v1', credentials=creds)

    # 3. Fetch list of 5 messages
    print("📡 Contacting Gmail API...")
    profile = service.users().getProfile(userId='me').execute()
    print(f"👤 Account: {profile['emailAddress']}")
    
    results = service.users().messages().list(userId='me', maxResults=5).execute()
    messages = results.get('messages', [])

    if not messages:
        print("Empty inbox or no messages found.")
        return

    print(f"\n✅ FIRST CONTACT SUCCESSFUL! Found {len(messages)} messages:\n")
    for msg in messages:
        m = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = m['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        print(f"🔹 Subject: {subject}")
        print(f"   Snippet: {m.get('snippet', '')[:70]}...")
        print("-" * 30)

if __name__ == "__main__":
    fetch_test()
