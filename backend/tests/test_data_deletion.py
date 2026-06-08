"""
DATA-DELETION-01 — DELETE /api/user endpoint tests.

12 tests covering:
  - Validation: missing/false confirm, wrong phrase
  - Store unavailability (503)
  - RPC failure (500)
  - Success: store called, cookie cleared, response shape
  - Auth: unauthenticated request returns 401
  - Audit log ordering before deletion
  - UID vs sub routing
  - Edge cases: no accounts removed, partial result
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.tests.test_account_membership import FakeStore
from backend.auth_guard import JWTClaims

TEST_JWT_SECRET = "dd01-deletion-test-secret-32bytes!!"

OWNER_CLAIMS = JWTClaims(
    sub="owner@gmail.com",
    uid="b3a99977-0d85-4530-8550-7c518fba4b96",
)

CONFIRM_BODY = {
    "confirm": True,
    "confirm_phrase": "DELETE MY ACCOUNT",
}


class FakeStoreWithDeletion(FakeStore):
    def __init__(self, deletion_result=None, deletion_raises=None):
        super().__init__()
        self._deletion_result = deletion_result or {
            "status": "deleted",
            "accounts_removed": 2,
            "rows_removed": 100,
        }
        self._deletion_raises = deletion_raises
        self.delete_user_data_called_with = None
        self.event_log = []
        self.client = MagicMock()
        self.client.table.return_value.insert.return_value.execute.side_effect = (
            lambda *args, **kwargs: self.event_log.append("audit_log_execute")
        )

    def delete_user_data(self, uid: str) -> dict:
        self.event_log.append("delete_user_data")
        self.delete_user_data_called_with = uid
        if self._deletion_raises:
            raise self._deletion_raises
        return self._deletion_result


def _reset_jwt_cache():
    from backend import auth_guard as ag
    ag._JWT_SECRET = None


def _make_token(claims: JWTClaims) -> str:
    from backend import auth_guard as ag
    with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
        _reset_jwt_cache()
        return ag.create_access_token(subject=claims.sub, uid=claims.uid)


class TestDeleteUser(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)

    def setUp(self):
        _reset_jwt_cache()

    def _req(self, store, body=None):
        from backend.api import service
        from fastapi.testclient import TestClient
        token = _make_token(OWNER_CLAIMS)
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            with patch.object(service, "safe_get_store", return_value=store):
                client = TestClient(service.app, raise_server_exceptions=False)
                return client.request(
                    "DELETE",
                    "/api/user",
                    json=body,
                    cookies={"iea_session": token},
                )

    def test_delete_user_missing_confirm_returns_400(self):
        store = FakeStoreWithDeletion()
        resp = self._req(store, body={"confirm": False, "confirm_phrase": "DELETE MY ACCOUNT"})
        self.assertEqual(resp.status_code, 400)

    def test_delete_user_wrong_phrase_returns_400(self):
        store = FakeStoreWithDeletion()
        resp = self._req(store, body={"confirm": True, "confirm_phrase": "delete my account"})
        self.assertEqual(resp.status_code, 400)

    def test_delete_user_correct_confirmation_calls_store(self):
        store = FakeStoreWithDeletion()
        resp = self._req(store, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(store.delete_user_data_called_with, OWNER_CLAIMS.uid)

    def test_delete_user_store_unavailable_returns_503(self):
        resp = self._req(store=None, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["detail"], "Storage unavailable")

    def test_delete_user_rpc_failure_returns_500(self):
        store = FakeStoreWithDeletion(deletion_raises=RuntimeError("RPC failed"))
        resp = self._req(store, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(
            resp.json()["detail"],
            "Deletion failed. The operation was rolled back.",
        )

    def test_delete_user_clears_session_cookie_on_success(self):
        store = FakeStoreWithDeletion()
        resp = self._req(store, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 200)
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertIn("iea_session", set_cookie)

    def test_delete_user_returns_correct_response_shape(self):
        store = FakeStoreWithDeletion()
        resp = self._req(store, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "deleted")
        self.assertIn("accounts_removed", data)
        self.assertIn("rows_removed", data)

    def test_delete_user_requires_jwt_auth(self):
        from backend.api import service
        from fastapi.testclient import TestClient
        store = FakeStoreWithDeletion()
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            with patch.object(service, "safe_get_store", return_value=store):
                client = TestClient(service.app, raise_server_exceptions=False)
                resp = client.request("DELETE", "/api/user", json=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 401)

    def test_delete_user_audit_log_written_before_deletion(self):
        store = FakeStoreWithDeletion()
        resp = self._req(store, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("audit_log_execute", store.event_log)
        self.assertIn("delete_user_data", store.event_log)
        self.assertLess(
            store.event_log.index("audit_log_execute"),
            store.event_log.index("delete_user_data"),
        )
        store.client.table.assert_called_with("audit_log")

    def test_delete_user_rpc_receives_uid_not_sub(self):
        store = FakeStoreWithDeletion()
        resp = self._req(store, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            store.delete_user_data_called_with,
            "b3a99977-0d85-4530-8550-7c518fba4b96",
        )
        self.assertNotEqual(store.delete_user_data_called_with, "owner@gmail.com")

    def test_delete_user_no_accounts_returns_gracefully(self):
        store = FakeStoreWithDeletion(deletion_result={
            "status": "deleted",
            "accounts_removed": 0,
            "rows_removed": 0,
        })
        resp = self._req(store, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["accounts_removed"], 0)
        self.assertEqual(data["rows_removed"], 0)

    def test_delete_user_partial_result_still_returns_200(self):
        store = FakeStoreWithDeletion(deletion_result={
            "status": "deleted",
            "accounts_removed": 1,
            "rows_removed": 50,
        })
        resp = self._req(store, body=CONFIRM_BODY)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "deleted")
        self.assertEqual(data["accounts_removed"], 1)
        self.assertEqual(data["rows_removed"], 50)
