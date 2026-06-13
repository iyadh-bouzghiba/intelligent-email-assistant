"""
SENT-TAB-REPAIR-01 — Route-level proof for rendered endpoint account_id behavior.

Three deterministic TestClient tests proving HTTP GET route behavior:
  1. GET /api/emails/{id}/rendered?account_id=<owned>   → 200, owned account used for lookup
  2. GET /api/emails/{id}/rendered?account_id=<unowned> → 403, ownership blocks unowned account
  3. GET /api/emails/{id}/rendered (no account_id)      → 200, primary-account fallback used

_require_account_ownership is NOT mocked — it executes normally against a fake store.
No real Supabase, Gmail, Mistral, or network required.

Run with:
    python -m unittest backend.tests.test_sent_rendered_account
from the repository root.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import backend.api.service as service  # noqa: E402
from backend.auth_guard import JWTClaims  # noqa: E402
from backend.tests.test_account_membership import FakeStore  # noqa: E402

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

USER_UID = "user-123"
OWNED_ACCOUNT = "owned@example.com"
PRIMARY_ACCOUNT = "primary@example.com"
UNOWNED_ACCOUNT = "evil@example.com"
MESSAGE_ID = "msg-123"

_FAKE_RECORD = {"account_id": OWNED_ACCOUNT, "body": "Hello, world."}
_FAKE_PAYLOAD = {
    "body_html": "<p>Hello, world.</p>",
    "body_text": "Hello, world.",
    "attachments": [],
    "linked_files": [],
}

_RENDERED_URL = f"/api/emails/{MESSAGE_ID}/rendered"


def _fake_claims() -> JWTClaims:
    return JWTClaims(sub=OWNED_ACCOUNT, uid=USER_UID)


def _store_with_owned() -> FakeStore:
    # OWNED_ACCOUNT is a known membership; PRIMARY_ACCOUNT is the primary fallback.
    return FakeStore(owned_accounts=[OWNED_ACCOUNT], primary=PRIMARY_ACCOUNT)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRenderedRouteAccountIdBehavior(unittest.TestCase):
    """
    Route-level proof via FastAPI TestClient.
    _require_account_ownership runs normally against FakeStore — it is never
    patched directly.
    """

    def setUp(self):
        # Override require_jwt_auth so routes receive deterministic JWTClaims
        # without needing a real JWT token or secret.
        service.app.dependency_overrides[service.require_jwt_auth] = _fake_claims
        self.client = TestClient(service.app, raise_server_exceptions=False)

    def tearDown(self):
        service.app.dependency_overrides.clear()

    # 1 — owned account_id → HTTP 200, owned account used for lookup
    def test_rendered_with_owned_account_id_passes(self):
        """
        GET ?account_id=OWNED_ACCOUNT
          - _require_account_ownership calls check_membership → True
          - _lookup_email_record_by_message_id receives OWNED_ACCOUNT
          - response is HTTP 200 with gmail_message_id in JSON
        """
        lookup_spy = MagicMock(return_value=_FAKE_RECORD)
        build_spy = MagicMock(return_value=_FAKE_PAYLOAD)

        with patch.object(service, "safe_get_store", return_value=_store_with_owned()), \
             patch.object(service, "_lookup_email_record_by_message_id", lookup_spy), \
             patch.object(service, "_build_rendered_email_payload", build_spy):

            response = self.client.get(
                _RENDERED_URL,
                params={"account_id": OWNED_ACCOUNT},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["gmail_message_id"], MESSAGE_ID)
        # Ownership resolved to OWNED_ACCOUNT — lookup must have received it
        lookup_spy.assert_called_once_with(OWNED_ACCOUNT, MESSAGE_ID)

    # 2 — unowned account_id → HTTP 403, lookup never called
    def test_rendered_with_wrong_account_id_returns_403(self):
        """
        GET ?account_id=UNOWNED_ACCOUNT
          - _require_account_ownership calls check_membership → False → raises 403
          - _lookup_email_record_by_message_id is never reached
        """
        lookup_spy = MagicMock(return_value=_FAKE_RECORD)

        with patch.object(service, "safe_get_store", return_value=_store_with_owned()), \
             patch.object(service, "_lookup_email_record_by_message_id", lookup_spy):

            response = self.client.get(
                _RENDERED_URL,
                params={"account_id": UNOWNED_ACCOUNT},
            )

        self.assertEqual(response.status_code, 403)
        lookup_spy.assert_not_called()

    # 3 — no account_id → HTTP 200, primary fallback used for lookup
    def test_rendered_without_account_id_uses_primary_fallback(self):
        """
        GET (no account_id param)
          - _require_account_ownership calls get_primary_account → PRIMARY_ACCOUNT
          - _lookup_email_record_by_message_id receives PRIMARY_ACCOUNT
          - response is HTTP 200 with gmail_message_id in JSON
        """
        lookup_spy = MagicMock(return_value=_FAKE_RECORD)
        build_spy = MagicMock(return_value=_FAKE_PAYLOAD)

        with patch.object(service, "safe_get_store", return_value=_store_with_owned()), \
             patch.object(service, "_lookup_email_record_by_message_id", lookup_spy), \
             patch.object(service, "_build_rendered_email_payload", build_spy):

            response = self.client.get(_RENDERED_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["gmail_message_id"], MESSAGE_ID)
        # No account_id provided → primary fallback used
        lookup_spy.assert_called_once_with(PRIMARY_ACCOUNT, MESSAGE_ID)


if __name__ == "__main__":
    unittest.main()
