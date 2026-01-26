import os, json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def fetch_report():
    with open('data/store.json', 'r') as f:
        data = json.load(f)
    
    creds = Credentials(
        token=data['token'],
        refresh_token=data.get('refresh_token'),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=data['client_id'],
        client_secret=data['client_secret']
    )

    service = build('gmail', 'v1', credentials=creds)
    profile = service.users().getProfile(userId='me').execute()
    email = profile['emailAddress']
    
    results = service.users().messages().list(userId='me', maxResults=5).execute()
    messages = results.get('messages', [])

    report = {
        "account": email,
        "emails": []
    }

    for msg in messages:
        m = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = m['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        report["emails"].append({
            "subject": subject,
            "snippet": m.get('snippet', '')
        })

    with open('fetch_report.json', 'w') as f:
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    fetch_report()
