"""
MUI01-R1-C — Route-level account isolation tests.

28 tests covering:
  - 24 route isolation tests (12 routes x 2: unowned 403, owned non-403)
  - test_send_on_conflict_is_composite
  - test_root_emails_route_removed
  - test_first_ever_oauth_new_user_creates_uuid_and_membership
  - test_ownership_check_uses_uid_not_sub
"""

import inspect
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.tests.test_account_membership import FakeStore
from backend.auth_guard import JWTClaims

TEST_JWT_SECRET = "r1c-isolation-test-secret-32bytes!!"
ACCESS_DENIED = "Access denied: account does not belong to the authenticated session."

OWNED_CLAIMS = JWTClaims(
    sub="owner@gmail.com",
    uid="b3a99977-0d85-4530-8550-7c518fba4b96",
)

UNOWNED_CLAIMS = JWTClaims(
    sub="attacker@gmail.com",
    uid="00000000-0000-0000-0000-000000000001",
)

OWNED_ACCOUNT_ID = "owner@gmail.com"


def _reset_jwt_cache():
    from backend import auth_guard as ag
    ag._JWT_SECRET = None


def _make_token(claims: JWTClaims) -> str:
    from backend import auth_guard as ag
    with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
        _reset_jwt_cache()
        return ag.create_access_token(subject=claims.sub, uid=claims.uid)


def _owned_store() -> FakeStore:
    store = FakeStore(owned_accounts=[OWNED_ACCOUNT_ID], primary=OWNED_ACCOUNT_ID)
    store.client = MagicMock()
    return store


def _unowned_store() -> FakeStore:
    return FakeStore(owned_accounts=[], primary=None)


class TestR1CIsolation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)

    def setUp(self):
        _reset_jwt_cache()

    def _req(self, method, url, claims, store, *, json=None):
        from backend.api import service
        from fastapi.testclient import TestClient
        token = _make_token(claims)
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            with patch.object(service, "safe_get_store", return_value=store):
                client = TestClient(service.app, raise_server_exceptions=False)
                kwargs = {}
                if json is not None:
                    kwargs["json"] = json
                return getattr(client, method.lower())(
                    url, cookies={"iea_session": token}, **kwargs
                )

    # ── Route 1: GET /api/threads ─────────────────────────────────────────────

    def test_threads_unowned_returns_403(self):
        resp = self._req(
            "GET", f"/api/threads?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_threads_owned_returns_200_or_expected(self):
        resp = self._req(
            "GET", f"/api/threads?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 2: GET /api/sent ────────────────────────────────────────────────

    def test_sent_unowned_returns_403(self):
        resp = self._req(
            "GET", f"/api/sent?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_sent_owned_returns_200_or_expected(self):
        resp = self._req(
            "GET", f"/api/sent?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 3: GET /api/threads/{thread_id}/messages ────────────────────────

    def test_thread_messages_unowned_returns_403(self):
        resp = self._req(
            "GET",
            f"/api/threads/test-thread-id/messages?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_thread_messages_owned_returns_200_or_expected(self):
        resp = self._req(
            "GET",
            f"/api/threads/test-thread-id/messages?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 4: POST /api/backfill-sent ──────────────────────────────────────

    def test_backfill_sent_unowned_returns_403(self):
        resp = self._req(
            "POST", f"/api/backfill-sent?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_backfill_sent_owned_returns_200_or_expected(self):
        resp = self._req(
            "POST", f"/api/backfill-sent?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 5: POST /api/maintenance/correct-inbox-attachments ─────────────

    def test_maintenance_correct_inbox_attachments_unowned_returns_403(self):
        resp = self._req(
            "POST",
            f"/api/maintenance/correct-inbox-attachments?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_maintenance_correct_inbox_attachments_owned_returns_200_or_expected(self):
        resp = self._req(
            "POST",
            f"/api/maintenance/correct-inbox-attachments?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 6: POST /api/maintenance/correct-sent-attachments ──────────────

    def test_maintenance_correct_sent_attachments_unowned_returns_403(self):
        resp = self._req(
            "POST",
            f"/api/maintenance/correct-sent-attachments?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_maintenance_correct_sent_attachments_owned_returns_200_or_expected(self):
        resp = self._req(
            "POST",
            f"/api/maintenance/correct-sent-attachments?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 7: GET /api/templates ───────────────────────────────────────────

    def test_templates_unowned_returns_403(self):
        resp = self._req(
            "GET", f"/api/templates?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_templates_owned_returns_200_or_expected(self):
        resp = self._req(
            "GET", f"/api/templates?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 8: POST /api/templates ──────────────────────────────────────────

    def test_templates_create_unowned_returns_403(self):
        body = {
            "account_id": OWNED_ACCOUNT_ID,
            "name": "Test Template",
            "language": "en",
            "body": "Hello world",
        }
        resp = self._req("POST", "/api/templates", UNOWNED_CLAIMS, _unowned_store(), json=body)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_templates_create_owned_returns_200_or_expected(self):
        body = {
            "account_id": OWNED_ACCOUNT_ID,
            "name": "Test Template",
            "language": "en",
            "body": "Hello world",
        }
        resp = self._req("POST", "/api/templates", OWNED_CLAIMS, _owned_store(), json=body)
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 9: DELETE /api/templates/{template_id} ──────────────────────────

    def test_templates_delete_unowned_returns_403(self):
        resp = self._req(
            "DELETE",
            f"/api/templates/some-template-id?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_templates_delete_owned_returns_200_or_expected(self):
        resp = self._req(
            "DELETE",
            f"/api/templates/some-template-id?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 10: POST /api/agent/consent ─────────────────────────────────────

    def test_agent_consent_unowned_returns_403(self):
        body = {"account_id": OWNED_ACCOUNT_ID}
        resp = self._req("POST", "/api/agent/consent", UNOWNED_CLAIMS, _unowned_store(), json=body)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_agent_consent_owned_returns_200_or_expected(self):
        body = {"account_id": OWNED_ACCOUNT_ID}
        resp = self._req("POST", "/api/agent/consent", OWNED_CLAIMS, _owned_store(), json=body)
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 11: GET /api/agent/status ───────────────────────────────────────

    def test_agent_status_unowned_returns_403(self):
        resp = self._req(
            "GET", f"/api/agent/status?account_id={OWNED_ACCOUNT_ID}",
            UNOWNED_CLAIMS, _unowned_store(),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_agent_status_owned_returns_200_or_expected(self):
        resp = self._req(
            "GET", f"/api/agent/status?account_id={OWNED_ACCOUNT_ID}",
            OWNED_CLAIMS, _owned_store(),
        )
        self.assertNotEqual(resp.status_code, 403)

    # ── Route 12: POST /api/agent/feedback ────────────────────────────────────

    def test_agent_feedback_unowned_returns_403(self):
        body = {
            "account_id": OWNED_ACCOUNT_ID,
            "conversation_id": "conv-001",
            "action_type": "draft_reply",
            "subject": "Test subject",
            "outcome": "accepted",
        }
        resp = self._req("POST", "/api/agent/feedback", UNOWNED_CLAIMS, _unowned_store(), json=body)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], ACCESS_DENIED)

    def test_agent_feedback_owned_returns_200_or_expected(self):
        body = {
            "account_id": OWNED_ACCOUNT_ID,
            "conversation_id": "conv-001",
            "action_type": "draft_reply",
            "subject": "Test subject",
            "outcome": "accepted",
        }
        resp = self._req("POST", "/api/agent/feedback", OWNED_CLAIMS, _owned_store(), json=body)
        self.assertNotEqual(resp.status_code, 403)

    # ── Additional tests ──────────────────────────────────────────────────────

    def test_send_on_conflict_is_composite(self):
        from backend.api import service
        src = inspect.getsource(service)
        self.assertIn(
            'on_conflict="thread_id,account_id"',
            src,
            "send path must use composite on_conflict='thread_id,account_id'",
        )
        self.assertNotIn(
            'on_conflict="thread_id"',
            src,
            "old single-column on_conflict='thread_id' must be absent",
        )

    def test_root_emails_route_removed(self):
        from backend.api import service
        from fastapi.testclient import TestClient

        src = inspect.getsource(service)
        self.assertNotIn('@app.get("/emails"', src)

        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            client = TestClient(service.app, raise_server_exceptions=False)
            resp = client.get("/emails")
        self.assertEqual(resp.status_code, 404)

    def test_first_ever_oauth_new_user_creates_uuid_and_membership(self):
        from backend.api import service
        from backend.infrastructure.supabase_store import SupabaseStore

        src = inspect.getsource(service.google_oauth_callback)

        resolve_pos = src.find("resolve_uid_by_account")
        create_pos = src.find("get_or_create_app_user()")
        upsert_pos = src.find("upsert_membership")
        token_pos = src.find("create_access_token")

        self.assertGreater(resolve_pos, -1, "resolve_uid_by_account not found in oauth callback")
        self.assertGreater(create_pos, -1, "get_or_create_app_user() not found in oauth callback")
        self.assertGreater(upsert_pos, -1, "upsert_membership not found in oauth callback")
        self.assertGreater(token_pos, -1, "create_access_token not found in oauth callback")
        self.assertLess(upsert_pos, token_pos, "upsert_membership must precede create_access_token")
        self.assertIn("subject=effective_account_id", src)
        self.assertIn("uid=user_uid", src)

        mock_client = MagicMock()
        expected_uid = "b3a99977-0d85-4530-8550-7c518fba4b96"
        mock_client.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": expected_uid}
        ]

        store = SupabaseStore.__new__(SupabaseStore)
        store.client = mock_client

        result_uid = store.get_or_create_app_user()
        self.assertEqual(result_uid, expected_uid)
        mock_client.table.assert_any_call("app_users")

        mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
        store.upsert_membership(result_uid, "gmail", OWNED_ACCOUNT_ID)
        mock_client.table.assert_any_call("account_memberships")

    def test_ownership_check_uses_uid_not_sub(self):
        from backend.api import service
        from backend.api.service import _require_account_ownership

        class _RecordingStore:
            def __init__(self):
                self.received_uid = None

            def check_membership(self, user_uid, provider, account_id):
                self.received_uid = user_uid
                return True

            def get_primary_account(self, user_uid, provider):
                return None

        recording = _RecordingStore()
        test_uid = "uid-proof-999-not-a-sub-email"
        _require_account_ownership(test_uid, OWNED_ACCOUNT_ID, recording)
        self.assertEqual(recording.received_uid, test_uid)

        src = inspect.getsource(service)
        uid_calls = src.count("_require_account_ownership(claims.uid,")
        sub_calls = src.count("_require_account_ownership(claims.sub,")
        self.assertGreater(uid_calls, 0, "_require_account_ownership must be called with claims.uid")
        self.assertEqual(sub_calls, 0, "_require_account_ownership must never be called with claims.sub")


if __name__ == "__main__":
    unittest.main()
