"""
SOCKET-AUTH-01 - Socket.IO authentication helper tests.

These tests intentionally target backend.auth_guard helper logic instead of
importing backend.api.service, because service.py has known import-time stdout
side effects under pytest.
"""

import os
import time
import unittest
from unittest.mock import patch

import jwt
from fastapi import HTTPException

from backend import auth_guard as ag


TEST_SECRET = "sockauth01-test-secret-with-at-least-32-bytes"


def _reset_cached_secret():
    ag._JWT_SECRET = None


class TestSocketAuthHelpers(unittest.TestCase):
    def setUp(self):
        _reset_cached_secret()

    def tearDown(self):
        _reset_cached_secret()

    def _auth_env(self):
        return patch.dict(os.environ, {"JWT_SECRET": TEST_SECRET}, clear=False)

    def _create_token(self, subject):
        with self._auth_env():
            _reset_cached_secret()
            return ag.create_access_token(subject)

    def _encode_payload(self, payload):
        return jwt.encode(payload, TEST_SECRET, algorithm="HS256")

    def test_missing_cookie_and_auth_payload_are_rejected(self):
        with self._auth_env():
            _reset_cached_secret()
            with self.assertRaises(HTTPException) as ctx:
                ag.resolve_socket_auth_subject({}, None)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Authentication required")

    def test_legacy_auth_token_cookie_is_ignored_and_rejected(self):
        token = self._create_token("sockauth@example.com")
        environ = {"HTTP_COOKIE": f"auth_token={token}"}

        with self._auth_env():
            _reset_cached_secret()
            with self.assertRaises(HTTPException) as ctx:
                ag.resolve_socket_auth_subject(environ, None)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Authentication required")

    def test_invalid_iea_session_cookie_is_rejected(self):
        environ = {"HTTP_COOKIE": "iea_session=not-a-valid-jwt"}

        with self._auth_env():
            _reset_cached_secret()
            with self.assertRaises(HTTPException) as ctx:
                ag.resolve_socket_auth_subject(environ, None)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid session token")

    def test_valid_iea_session_cookie_returns_subject(self):
        token = self._create_token("sockauth@example.com")
        environ = {
            "HTTP_COOKIE": f"theme=dark; iea_session={token}; other=value"
        }

        with self._auth_env():
            _reset_cached_secret()
            subject = ag.resolve_socket_auth_subject(environ, None)

        self.assertEqual(subject, "sockauth@example.com")

    def test_valid_asgi_scope_cookie_header_returns_subject(self):
        token = self._create_token("scope-cookie@example.com")
        environ = {
            "asgi.scope": {
                "headers": [
                    (b"host", b"example.test"),
                    (b"cookie", f"iea_session={token}".encode("latin-1")),
                ],
            }
        }

        with self._auth_env():
            _reset_cached_secret()
            subject = ag.resolve_socket_auth_subject(environ, None)

        self.assertEqual(subject, "scope-cookie@example.com")

    def test_valid_auth_payload_token_returns_subject(self):
        token = self._create_token("payload-token@example.com")

        with self._auth_env():
            _reset_cached_secret()
            subject = ag.resolve_socket_auth_subject({}, {"token": token})

        self.assertEqual(subject, "payload-token@example.com")

    def test_valid_auth_payload_access_token_alias_returns_subject(self):
        token = self._create_token("payload-access-token@example.com")

        with self._auth_env():
            _reset_cached_secret()
            subject = ag.resolve_socket_auth_subject(
                {},
                {"access_token": token},
            )

        self.assertEqual(subject, "payload-access-token@example.com")

    def test_empty_subject_token_is_rejected(self):
        now = int(time.time())
        token = self._encode_payload({"sub": "", "iat": now, "exp": now + 60})
        environ = {"HTTP_COOKIE": f"iea_session={token}"}

        with self._auth_env():
            _reset_cached_secret()
            with self.assertRaises(HTTPException) as ctx:
                ag.resolve_socket_auth_subject(environ, None)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid session token")

    def test_expired_token_is_rejected(self):
        now = int(time.time())
        token = self._encode_payload(
            {"sub": "expired@example.com", "iat": now - 120, "exp": now - 60}
        )
        environ = {"HTTP_COOKIE": f"iea_session={token}"}

        with self._auth_env():
            _reset_cached_secret()
            with self.assertRaises(HTTPException) as ctx:
                ag.resolve_socket_auth_subject(environ, None)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Session expired")


if __name__ == "__main__":
    unittest.main()
