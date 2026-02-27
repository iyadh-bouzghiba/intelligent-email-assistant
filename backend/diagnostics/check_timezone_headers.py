"""
Diagnostic script to inspect Date header timezones across Gmail accounts.

This script fetches recent emails from each account and logs:
- Raw Date header from Gmail
- Parsed datetime with timezone
- Converted UTC timestamp
- Timezone offset detected

Run this to diagnose why different accounts show different times.
"""

import sys
import os
import json
from pathlib import Path
from email.utils import parsedate_to_datetime
from datetime import timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.auth.credential_store import CredentialStore
from backend.data.store import PersistenceManager
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def check_account_timezone(account_id: str):
    """Check timezone info for recent emails from specific account."""
    print(f"\n{'='*80}")
    print(f"🔍 CHECKING ACCOUNT: {account_id}")
    print(f"{'='*80}\n")

    # Load credentials
    persistence = PersistenceManager()
    credential_store = CredentialStore(persistence)
    token_data = credential_store.load_credentials(account_id)

    if not token_data:
        print(f"❌ No credentials found for account: {account_id}")
        return

    # Build Gmail service
    try:
        creds = Credentials(
            token=token_data['token'],
            refresh_token=token_data.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_data['client_id'],
            client_secret=token_data['client_secret']
        )
        service = build('gmail', 'v1', credentials=creds)
    except Exception as e:
        print(f"❌ Failed to build Gmail service: {e}")
        return

    # Fetch 5 most recent emails
    try:
        results = service.users().messages().list(
            userId='me',
            q='in:inbox',
            maxResults=5
        ).execute()

        messages = results.get('messages', [])
        if not messages:
            print("📭 No emails found in inbox")
            return

        print(f"📬 Found {len(messages)} recent emails\n")

        for idx, msg_info in enumerate(messages, 1):
            msg = service.users().messages().get(userId='me', id=msg_info['id']).execute()
            payload = msg.get('payload', {})
            headers = payload.get('headers', [])

            # Extract subject and Date header
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "No Subject")
            date_header = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)
            internal_date_ms = msg.get('internalDate')

            print(f"📧 Email #{idx}: {subject[:50]}")
            print(f"   Raw Date Header: {date_header}")

            if date_header:
                try:
                    # Parse Date header (preserves timezone)
                    parsed_dt = parsedate_to_datetime(date_header)

                    # Check timezone info
                    if parsed_dt.tzinfo is None:
                        print(f"   ⚠️  Parsed datetime has NO timezone info (assuming UTC)")
                        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                        tz_offset = "+00:00"
                    else:
                        # Get UTC offset
                        utc_offset = parsed_dt.utcoffset()
                        if utc_offset:
                            total_seconds = int(utc_offset.total_seconds())
                            hours = total_seconds // 3600
                            minutes = (total_seconds % 3600) // 60
                            tz_offset = f"{hours:+03d}:{minutes:02d}"
                        else:
                            tz_offset = "+00:00"

                    # Convert to UTC for consistent storage
                    utc_dt = parsed_dt.astimezone(timezone.utc)

                    print(f"   📅 Parsed datetime: {parsed_dt.isoformat()}")
                    print(f"   🌍 Timezone offset: {tz_offset}")
                    print(f"   🕐 UTC datetime: {utc_dt.isoformat()}")

                except Exception as e:
                    print(f"   ❌ Failed to parse Date header: {e}")

            if internal_date_ms:
                from datetime import datetime
                internal_dt = datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)
                print(f"   🔢 Gmail internalDate: {internal_dt.isoformat()}")

            print()

    except Exception as e:
        print(f"❌ Failed to fetch emails: {e}")


def main():
    """Check timezone info for all connected accounts."""
    print("\n" + "="*80)
    print("⏰ GMAIL DATE HEADER TIMEZONE DIAGNOSTIC")
    print("="*80)

    # Check known accounts
    accounts = [
        "iyadh.bouzghiba.eng@gmail.com",
        "iyadh3004@gmail.com",
        "iyadhbouzghiba3@gmail.com"
    ]

    for account_id in accounts:
        check_account_timezone(account_id)

    print("\n" + "="*80)
    print("✅ DIAGNOSTIC COMPLETE")
    print("="*80)
    print("\n📊 SUMMARY:")
    print("- If all accounts show same timezone offset → issue is in display logic")
    print("- If accounts show different offsets → issue is in Date header normalization")
    print("- Expected fix: Normalize all timestamps to UTC before storage\n")


if __name__ == "__main__":
    main()
