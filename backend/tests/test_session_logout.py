"""SESSION-LOGOUT-01 - session logout cookie-clear tests."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from backend import auth_guard as ag

TEST_SECRET = "session-logout-01-test-secret-with-at-least-32-bytes"


def _reset_cached_secret():
    ag._JWT_SECRET = None


def _request_for_scheme(scheme):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": scheme,
            "path": "/",
            "headers": [],
            "server": ("testserver", 443 if scheme == "https" else 80),
        }
    )


class _FakeCredentialStore:
    deleted_accounts = []

    def __init__(self, *_args, **_kwargs):
        pass

    def delete_credentials(self, account_id):
        self.__class__.deleted_accounts.append(account_id)


class _FakeExecuteResponse:
    data = [{"account_id": "primary@example.com"}]


class _FakeCredentialDeleteQuery:
    def eq(self, field, value):
        self.field = field
        self.value = value
        return self

    def execute(self):
        return _FakeExecuteResponse()


class _FakeCredentialTable:
    def delete(self):
        return _FakeCredentialDeleteQuery()


class _FakeSupabaseClient:
    def table(self, name):
        assert name == "credentials"
        return _FakeCredentialTable()


class _FakeStore:
    client = _FakeSupabaseClient()


class TestSessionLogoutCookieHelpers(unittest.TestCase):
    def setUp(self):
        _reset_cached_secret()

    def tearDown(self):
        _reset_cached_secret()

    def test_cookie_clear_kwargs_http_mode(self):
        request = _request_for_scheme("http")

        cookie_kwargs = ag.build_session_cookie_clear_kwargs(request)

        self.assertEqual(cookie_kwargs["key"], "iea_session")
        self.assertEqual(cookie_kwargs["value"], "")
        self.assertTrue(cookie_kwargs["httponly"])
        self.assertEqual(cookie_kwargs["path"], "/")
        self.assertEqual(cookie_kwargs["max_age"], 0)
        self.assertEqual(cookie_kwargs["expires"], 0)
        self.assertEqual(cookie_kwargs["samesite"], "lax")
        self.assertFalse(cookie_kwargs["secure"])

    def test_cookie_clear_kwargs_https_mode(self):
        request = _request_for_scheme("https")

        cookie_kwargs = ag.build_session_cookie_clear_kwargs(request)

        self.assertEqual(cookie_kwargs["key"], "iea_session")
        self.assertEqual(cookie_kwargs["value"], "")
        self.assertEqual(cookie_kwargs["max_age"], 0)
        self.assertEqual(cookie_kwargs["expires"], 0)
        self.assertEqual(cookie_kwargs["samesite"], "none")
        self.assertTrue(cookie_kwargs["secure"])


class TestSessionLogoutRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("JWT_SECRET", TEST_SECRET)
        _reset_cached_secret()

        from backend.api import service

        cls.service = service
        cls.client = TestClient(service.app)

    def setUp(self):
        _FakeCredentialStore.deleted_accounts = []
        _reset_cached_secret()

    def tearDown(self):
        _reset_cached_secret()

    def _cookie(self, subject):
        with patch.dict(os.environ, {"JWT_SECRET": TEST_SECRET}, clear=False):
            _reset_cached_secret()
            token = ag.create_access_token(subject)
        return {"iea_session": token}

    def test_disconnect_account_clears_cookie_when_account_matches_subject(self):
        with patch.object(self.service, "CredentialStore", _FakeCredentialStore):
            response = self.client.post(
                "/api/accounts/active%40example.com/disconnect",
                cookies=self._cookie("active@example.com"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "disconnected", "account_id": "active@example.com"},
        )
        self.assertEqual(_FakeCredentialStore.deleted_accounts, ["active@example.com"])

        set_cookie = response.headers.get("set-cookie", "").lower()
        self.assertIn("iea_session=", set_cookie)
        self.assertIn("max-age=0", set_cookie)

    def test_disconnect_account_does_not_clear_cookie_for_non_subject_account(self):
        with patch.object(self.service, "CredentialStore", _FakeCredentialStore):
            response = self.client.post(
                "/api/accounts/secondary%40example.com/disconnect",
                cookies=self._cookie("active@example.com"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "disconnected", "account_id": "secondary@example.com"},
        )
        self.assertEqual(
            _FakeCredentialStore.deleted_accounts,
            ["secondary@example.com"],
        )

        set_cookie = response.headers.get("set-cookie", "").lower()
        self.assertNotIn("iea_session", set_cookie)

    def test_disconnect_all_accounts_always_clears_cookie_on_success(self):
        with patch.object(self.service, "safe_get_store", return_value=_FakeStore()):
            response = self.client.post(
                "/api/accounts/disconnect-all",
                cookies=self._cookie("active@example.com"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "deleted_count": 1})

        set_cookie = response.headers.get("set-cookie", "").lower()
        self.assertIn("iea_session=", set_cookie)
        self.assertIn("max-age=0", set_cookie)
