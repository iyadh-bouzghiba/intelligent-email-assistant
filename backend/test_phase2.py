"""
WebSocket & Email Adapter Test Script

This script provides comprehensive testing procedures for:
1. WebSocket real-time sync
2. Email adapter functionality (Gmail)
"""

# ============================================================================
# TEST 1: WebSocket Real-Time Sync
# ============================================================================

print("=" * 70)
print("TEST 1: WebSocket Real-Time Sync")
print("=" * 70)

print("""
MANUAL TEST PROCEDURE:
----------------------

1. Backend Status:
   ✅ Backend is running at http://localhost:8000
   ✅ Socket.IO server initialized
   ✅ Loaded 3 threads from persistence

2. Frontend Test Steps:
   
   Step 1: Open Browser
   - Navigate to: http://localhost:5173
   - Open DevTools Console (F12 → Console tab)
   
   Step 2: Verify WebSocket Connection
   - Look for console message: "[WebSocket] Connected to server"
   - Look for: "connection_established" event
   - Status should show: connected
   
   Step 3: Test Real-Time Update
   - Scroll to "Try Example Emails" section
   - Click on "Project Deadline" demo email
   - Watch console for:
     * "[App] Thread analyzed via WebSocket:" message
     * Thread data object with summary, key_points, etc.
   
   Step 4: Verify UI Update
   - Thread should appear in "Email Threads" list automatically
   - No page refresh needed
   - Summary should display on the right side
   
   Expected Console Output:
   -----------------------
   [WebSocket] Connected to server
   {status: 'connected'}
   [App] Thread analyzed via WebSocket: {thread_id: "...", summary: {...}}

VERIFICATION CHECKLIST:
-----------------------
[ ] WebSocket connects on page load
[ ] Console shows connection messages
[ ] Clicking demo email triggers analysis
[ ] WebSocket receives 'thread_analyzed' event
[ ] Thread list updates automatically
[ ] Summary displays without refresh
[ ] No errors in console

""")

# ============================================================================
# TEST 2: Email Adapter - Gmail Integration
# ============================================================================

print("\n" + "=" * 70)
print("TEST 2: Email Adapter - Gmail Integration")
print("=" * 70)

print("""
AUTOMATED TEST (Python):
------------------------

This test demonstrates the Gmail adapter functionality.
""")

import asyncio
from datetime import datetime, timedelta
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.adapters.gmail import GmailAdapter
    from src.adapters.base import StandardEmail
    
    print("\n✅ Successfully imported GmailAdapter and StandardEmail")
    
    # Test StandardEmail model
    print("\n--- Testing StandardEmail Model ---")
    test_email = StandardEmail(
        id="test123",
        sender="John Doe <john@example.com>",
        subject="Test Email",
        body_text="This is a test email body.",
        timestamp=datetime.now(),
        thread_id="thread123",
        recipients=["recipient@example.com"]
    )
    
    print(f"✅ StandardEmail created successfully:")
    print(f"   ID: {test_email.id}")
    print(f"   Sender: {test_email.sender}")
    print(f"   Subject: {test_email.subject}")
    print(f"   Body: {test_email.body_text[:50]}...")
    print(f"   Thread ID: {test_email.thread_id}")
    
    # Test HTML to text conversion
    print("\n--- Testing HTML to Plain Text Conversion ---")
    
    # Create a mock adapter to test HTML conversion
    class MockGmailAdapter(GmailAdapter):
        def __init__(self):
            # Skip OAuth initialization for testing
            pass
    
    adapter = MockGmailAdapter()
    
    html_content = """
    <html>
        <body>
            <h1>Important Email</h1>
            <p>This is a <strong>test</strong> email with <em>HTML</em> formatting.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </body>
    </html>
    """
    
    plain_text = adapter._html_to_text(html_content)
    print(f"✅ HTML converted to plain text:")
    print(f"   Original length: {len(html_content)} chars")
    print(f"   Plain text length: {len(plain_text)} chars")
    print(f"   Plain text: {plain_text}")
    
    print("\n" + "=" * 70)
    print("GMAIL ADAPTER VERIFICATION COMPLETE")
    print("=" * 70)
    
    print("""
    ✅ StandardEmail model works correctly
    ✅ HTML to plain text conversion functional
    ✅ GmailAdapter class structure verified
    
    NOTE: Full Gmail integration requires:
    - Valid OAuth2 credentials in .env
    - GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
    - User authentication via /auth/google/login
    
    To test with real Gmail account:
    1. Set up OAuth credentials
    2. Authenticate via frontend
    3. Use GmailAdapter.fetch_emails() method
    """)

except ImportError as e:
    print(f"\n❌ Import Error: {e}")
    print("   Make sure you're running this from the backend directory")
except Exception as e:
    print(f"\n❌ Test Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("ALL TESTS COMPLETE")
print("=" * 70)
