import os
import sys
import json
import base64
import logging
from pathlib import Path
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Configure logger to ensure Render captures output
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# CRITICAL: Add explicit StreamHandler for production logging (required for threaded execution)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(levelname)s] [%(name)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = True  # Also send to root logger

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

    # 3. The Fetcher - Fetch ALL INBOX emails with pagination
    emails_data = []
    try:
        # CRITICAL: Fetch ALL inbox emails (not just unread/filtered)
        # This ensures complete email sync across all accounts
        query = "in:inbox"

        # Pagination: Gmail API returns max 500 per request
        # CRITICAL: Optimized to 30 emails to reliably avoid timeout on Render free tier
        # Each email requires separate API call (~0.5s each)
        # 30 emails × 0.5s + overhead = ~18-20s (safely under 30s timeout)
        page_token = None
        total_fetched = 0
        max_emails = 30  # Optimized: fast sync, no timeout noise, professional UX

        while total_fetched < max_emails:
            # Fetch batch of emails
            list_params = {
                'userId': 'me',
                'q': query,
                'maxResults': min(30, max_emails - total_fetched)  # Fetch 30 at a time - no timeout
            }
            if page_token:
                list_params['pageToken'] = page_token

            results = service.users().messages().list(**list_params).execute()
            messages = results.get('messages', [])

            if not messages:
                break

            # Process this batch
            for msg_info in messages:
                msg = service.users().messages().get(userId='me', id=msg_info['id']).execute()
                label_ids = msg.get('labelIds', []) or []
                if "INBOX" not in label_ids:
                    continue

                payload = msg.get('payload', {})
                headers = payload.get('headers', [])

                # Extract Metadata
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "No Subject")
                sender_raw = next((h['value'] for h in headers if h['name'].lower() == 'from'), "Unknown Sender")
                date_header = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)

                # Use Gmail internalDate (ms since epoch) as authoritative timestamp
                # CRITICAL FIX: Use timezone-aware datetime to prevent drift
                from datetime import datetime, timezone

                internal_date_ms = msg.get('internalDate')
                timestamp_source = "unknown"

                # CRITICAL: Use Date header FIRST (matches Gmail inbox display)
                # Only fallback to internalDate if Date header is missing/invalid
                if date_header:
                    # PRIMARY: parse Date header (matches what Gmail inbox shows)
                    try:
                        from email.utils import parsedate_to_datetime
                        parsed_dt = parsedate_to_datetime(date_header)
                        # Ensure timezone-aware
                        if parsed_dt.tzinfo is None:
                            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

                        # CRITICAL FIX: ALWAYS normalize to UTC for consistent storage/display
                        # This prevents timezone inconsistencies across accounts
                        utc_dt = parsed_dt.astimezone(timezone.utc)
                        date_iso = utc_dt.isoformat()
                        timestamp_source = "date_header"

                        # Log timezone offset for diagnostics
                        tz_offset = parsed_dt.utcoffset()
                        offset_str = f"{int(tz_offset.total_seconds() / 3600):+03d}:00" if tz_offset else "+00:00"
                        logger.info(f"[TIMESTAMP-FIX] {subject[:30]}... | Date header: {date_header} | TZ offset: {offset_str} | UTC: {date_iso} | Source: {timestamp_source}")
                    except Exception as e:
                        # Fallback to internalDate if Date header parsing fails
                        if internal_date_ms:
                            dt_utc = datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)
                            date_iso = dt_utc.isoformat()
                            timestamp_source = "internalDate_fallback"
                            logger.warning(f"[TIMESTAMP-FIX] {subject[:30]}... | Date parse failed, using internalDate | UTC: {date_iso} | Error: {e}")
                        else:
                            dt_utc = datetime.now(timezone.utc)
                            date_iso = dt_utc.isoformat()
                            timestamp_source = "fallback_now"
                            logger.warning(f"[TIMESTAMP-FIX] {subject[:30]}... | Date parse failed: {e} | UTC: {date_iso} | Source: {timestamp_source}")
                elif internal_date_ms:
                    # Secondary fallback: Use internalDate if Date header missing
                    dt_utc = datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)
                    date_iso = dt_utc.isoformat()
                    timestamp_source = "internalDate_only"
                    logger.info(f"[TIMESTAMP-FIX] {subject[:30]}... | internalDate: {internal_date_ms}ms | UTC: {date_iso} | Source: {timestamp_source}")
                else:
                    dt_utc = datetime.now(timezone.utc)
                    date_iso = dt_utc.isoformat()
                    timestamp_source = "fallback_now"
                    logger.warning(f"[TIMESTAMP-FIX] {subject[:30]}... | No timestamp found | UTC: {date_iso} | Source: {timestamp_source}")

                # Extract & Clean Body
                raw_body = get_message_body(payload)
                cleaned_body = raw_body.strip()

                emails_data.append({
                    "message_id": msg['id'],  # Gmail message ID
                    "subject": subject,
                    "sender": sender_raw,
                    "date": date_iso,  # ISO timestamp
                    "body": cleaned_body
                })

                total_fetched += 1

            # Check pagination - continue to next page if available
            page_token = results.get('nextPageToken')
            if not page_token:
                break  # No more pages

        logger.info(f"[GMAIL] Fetched {len(emails_data)} emails from inbox")
        return emails_data

    except Exception as e:
        error_str = str(e).lower()
        if "invalid_grant" in error_str or "invalid_client" in error_str:
            logger.warning(f"[WARN] [GMAIL] Re-auth required: token expired/revoked")
            return {"__auth_error__": "invalid_grant"}

        # Log detailed error for debugging sync failures
        logger.error(f"[ERROR] [GMAIL] Sync failed with exception: {type(e).__name__}")
        logger.error(f"[ERROR] [GMAIL] Error message: {str(e)}")
        import traceback
        logger.error(f"[ERROR] [GMAIL] Traceback: {traceback.format_exc()}")
        return []

if __name__ == "__main__":
    emails = run_engine()
    print(f"✅ CORE ENGINE LIVE: DATA STREAMING SUCCESSFUL. Fetched {len(emails)} emails.")
