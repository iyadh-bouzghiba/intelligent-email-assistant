import os
import json
import base64
from pathlib import Path
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def clean_html(html_content):
    """Strips HTML tags to save context window space."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    # Remove script and style elements
    for script_or_style in soup(["script", "style"]):
        script_or_style.decompose()
    # Get text and handle whitespace
    text = soup.get_text(separator=' ')
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    cleaned_text = '\n'.join(chunk for chunk in chunks if chunk)
    return cleaned_text

def get_message_body(payload):
    """Recursively extracts and decodes the message body from Gmail payload."""
    body = ""
    if 'parts' in payload:
        for part in payload['parts']:
            body += get_message_body(part)
    else:
        if payload.get('mimeType') in ['text/plain', 'text/html']:
            data = payload.get('body', {}).get('data')
            if data:
                decoded_data = base64.urlsafe_b64decode(data).decode('utf-8')
                if payload.get('mimeType') == 'text/html':
                    body += clean_html(decoded_data)
                else:
                    body += decoded_data
    return body

def run_engine(token_data: dict):
    if not token_data or 'token' not in token_data:
        print("⚠️ Gmail Authentication Required. Please provide valid token data.")
        return []
    
    try:
        creds = Credentials(
            token=token_data['token'],
            refresh_token=token_data.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_data['client_id'],
            client_secret=token_data['client_secret']
        )
    except Exception as e:
        print(f"⚠️ Gmail Authentication Error: {str(e)}")
        return []

    # 2. Build Service
    service = build('gmail', 'v1', credentials=creds)

    # 3. The Fetcher - Looking for "Strategic" emails
    emails_data = []
    try:
        # Query for non-chat, non-newsletter content usually yields more strategic emails
        query = "-category:promotions -category:social is:unread"
        results = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
        messages = results.get('messages', [])

        if not messages:
            return []

        for msg_info in messages:
            msg = service.users().messages().get(userId='me', id=msg_info['id']).execute()
            payload = msg.get('payload', {})
            headers = payload.get('headers', [])

            # Extract Metadata
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "No Subject")
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), "Unknown Sender")
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), "Unknown Date")

            # Extract & Clean Body
            raw_body = get_message_body(payload)
            cleaned_body = raw_body.strip()

            emails_data.append({
                "subject": subject,
                "sender": sender,
                "date": date,
                "body": cleaned_body
            })

        return emails_data

    except Exception as e:
        print(f"❌ Error during execution: {str(e)}")
        return []

if __name__ == "__main__":
    emails = run_engine()
    print(f"✅ CORE ENGINE LIVE: DATA STREAMING SUCCESSFUL. Fetched {len(emails)} emails.")
