"""
MUI01-R1-B — Account membership model: focused unit tests.

8 tests covering:
  - JWT sub+uid payload contract
  - require_jwt_auth returns JWTClaims (including legacy uid-absent tokens)
  - _require_account_ownership: allow, block, exact 403 detail, None→primary
  - list_accounts membership-only query behavior
  - google_oauth_callback: upsert_membership before create_access_token
"""

import inspect
import os
import sys
import unittest
from typing import List, Optional
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

TEST_JWT_SECRET = "account-membership-test-secret-32bytes!!"
TEST_UID = "00000000-0000-4000-8000-000000000099"
OWNER = "owner@example.com"
OTHER = "other@example.com"
SECONDARY = "secondary@example.com"


# ── FakeStore ─────────────────────────────────────────────────────────────────

class FakeStore:
    def __init__(
        self,
        owned_accounts: Optional[List[str]] = None,
        primary: Optional[str] = None,
    ):
        self._owned = owned_accounts or []
        self._primary = primary

    def check_membership(self, user_uid, provider, account_id) -> bool:
        return account_id in self._owned

    def get_primary_account(self, user_uid, provider) -> Optional[str]:
        return self._primary

    def list_memberships(self, user_uid, provider) -> List[str]:
        return self._owned


# ── JWT secret cache helper ───────────────────────────────────────────────────

def _reset_jwt_cache():
    from backend import auth_guard as ag
    ag._JWT_SECRET = None


# ══════════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestAccountMembership(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)

    def setUp(self):
        _reset_jwt_cache()

    # ── 1. JWT payload contains sub and uid ───────────────────────────────────

    def test_jwt_contains_sub_and_uid(self):
        from backend import auth_guard as ag
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            token = ag.create_access_token(subject=OWNER, uid=TEST_UID)
            payload = ag.decode_access_token(token)

        self.assertEqual(payload["sub"], OWNER)
        self.assertEqual(payload["uid"], TEST_UID)
        self.assertIn("iat", payload)
        self.assertIn("exp", payload)

    # ── 2. require_jwt_auth returns JWTClaims with sub and uid ────────────────

    def test_require_jwt_auth_returns_jwtclaims(self):
        from backend import auth_guard as ag

        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            token = ag.create_access_token(subject=OWNER, uid=TEST_UID)

        request = MagicMock()
        request.cookies = {ag.COOKIE_NAME: token}
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            result = ag.require_jwt_auth(request)

        self.assertEqual(result.sub, OWNER)
        self.assertEqual(result.uid, TEST_UID)
        self.assertIsInstance(result, ag.JWTClaims)

        # Legacy transition: token with only sub and no uid must not raise;
        # uid field defaults to empty string.
        import jwt as _jwt
        import time
        legacy_payload = {
            "sub": OWNER,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        legacy_token = _jwt.encode(legacy_payload, TEST_JWT_SECRET, algorithm="HS256")
        legacy_request = MagicMock()
        legacy_request.cookies = {ag.COOKIE_NAME: legacy_token}
        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            legacy_result = ag.require_jwt_auth(legacy_request)
        self.assertEqual(legacy_result.sub, OWNER)
        self.assertEqual(legacy_result.uid, "")

    # ── 3. Owned secondary account is allowed through ─────────────────────────

    def test_ownership_allows_owned_secondary_account(self):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
        from backend.api.service import _require_account_ownership

        fake_store = FakeStore(owned_accounts=[SECONDARY], primary=OWNER)
        result = _require_account_ownership(TEST_UID, SECONDARY, fake_store)
        self.assertEqual(result, SECONDARY)

    # ── 4. Unowned account raises HTTP 403 ────────────────────────────────────

    def test_ownership_blocks_unowned_account_403(self):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
        from backend.api.service import _require_account_ownership
        from fastapi import HTTPException

        fake_store = FakeStore(owned_accounts=[OWNER])
        with self.assertRaises(HTTPException) as ctx:
            _require_account_ownership(TEST_UID, OTHER, fake_store)
        self.assertEqual(ctx.exception.status_code, 403)

    # ── 5. 403 detail string must be exactly as specified ────────────────────

    def test_ownership_403_detail_string_unchanged(self):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
        from backend.api.service import _require_account_ownership
        from fastapi import HTTPException

        fake_store = FakeStore(owned_accounts=[OWNER])
        with self.assertRaises(HTTPException) as ctx:
            _require_account_ownership(TEST_UID, OTHER, fake_store)
        self.assertEqual(
            ctx.exception.detail,
            "Access denied: account does not belong to the authenticated session.",
        )

    # ── 6. None account_id resolves to primary ────────────────────────────────

    def test_missing_account_id_resolves_primary(self):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
        from backend.api.service import _require_account_ownership

        fake_store = FakeStore(primary=OWNER)
        result = _require_account_ownership(TEST_UID, None, fake_store)
        self.assertEqual(result, OWNER)

    # ── 7. list_accounts uses membership filter and returns only owned ─────────

    def test_list_accounts_returns_membership_only(self):
        os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
        from backend import auth_guard as ag
        from backend.api import service

        with patch.dict(os.environ, {"JWT_SECRET": TEST_JWT_SECRET}, clear=False):
            _reset_jwt_cache()
            token = ag.create_access_token(subject=OWNER, uid=TEST_UID)

        from fastapi.testclient import TestClient

        # Track in_ call arguments to prove membership-filtered query.
        in_calls: List = []

        class _RecordingChain:
            def __init__(self, data=None):
                self._data = data or []
            def select(self, *a, **kw):
                return self
            def eq(self, *a, **kw):
                return self
            def in_(self, col, values):
                in_calls.append((col, list(values)))
                return self
            def execute(self):
                return type("R", (), {"data": self._data})()

        class _FakeClientWithRecording:
            def __init__(self, cred_rows):
                self._cred_rows = cred_rows
            def table(self, name):
                if name == "credentials":
                    return _RecordingChain(data=self._cred_rows)
                return _RecordingChain()

        owned_cred = {
            "account_id": OWNER,
            "provider": "gmail",
            "scopes": "https://www.googleapis.com/auth/gmail.readonly",
            "updated_at": None,
        }

        fake_store = FakeStore(owned_accounts=[OWNER], primary=OWNER)
        fake_store.client = _FakeClientWithRecording(cred_rows=[owned_cred])

        with patch.object(service, "safe_get_store", return_value=fake_store):
            with patch.object(service, "CredentialStore") as mock_cred_store_cls:
                mock_cred_instance = MagicMock()
                mock_cred_instance.load_credentials.return_value = {"token": "fake"}
                mock_cred_store_cls.return_value = mock_cred_instance

                client = TestClient(service.app)
                response = client.get(
                    "/api/accounts",
                    cookies={"iea_session": token},
                )

        self.assertEqual(response.status_code, 200)
        accounts = response.json().get("accounts", [])
        account_ids = [a["account_id"] for a in accounts]

        # Owned account must appear; unowned must not.
        self.assertIn(OWNER, account_ids)
        self.assertNotIn(OTHER, account_ids)

        # in_ must have been called with the owned account list.
        self.assertTrue(
            any(col == "account_id" and OWNER in vals for col, vals in in_calls),
            f"Expected in_(account_id, [...{OWNER}...]) but got: {in_calls}",
        )

    # ── 8. upsert_membership appears before create_access_token in oauth callback

    def test_oauth_upserts_membership_before_token(self):
        from backend.api import service

        src = inspect.getsource(service.google_oauth_callback)

        upsert_pos = src.find("store.upsert_membership")
        create_token_pos = src.find("create_access_token")
        resolve_uid_pos = src.find('resolve_uid_by_account("gmail", effective_account_id)')
        get_or_create_pos = src.find("get_or_create_app_user()")

        self.assertGreater(
            upsert_pos, -1,
            "store.upsert_membership not found in google_oauth_callback",
        )
        self.assertGreater(
            create_token_pos, -1,
            "create_access_token not found in google_oauth_callback",
        )
        self.assertLess(
            upsert_pos,
            create_token_pos,
            "store.upsert_membership must appear before create_access_token",
        )

        # create_access_token must use subject=effective_account_id and uid=user_uid.
        self.assertIn(
            "subject=effective_account_id",
            src,
            "create_access_token must be called with subject=effective_account_id",
        )
        self.assertIn(
            "uid=user_uid",
            src,
            "create_access_token must be called with uid=user_uid",
        )

        # resolve_uid_by_account and get_or_create_app_user must exist.
        self.assertGreater(
            resolve_uid_pos, -1,
            'resolve_uid_by_account("gmail", effective_account_id) not found',
        )
        self.assertGreater(
            get_or_create_pos, -1,
            "get_or_create_app_user() not found in google_oauth_callback",
        )


if __name__ == "__main__":
    unittest.main()
