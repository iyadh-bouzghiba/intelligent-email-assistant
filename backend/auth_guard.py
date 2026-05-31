import os
import time
from http.cookies import CookieError, SimpleCookie
from typing import Optional

import jwt
from fastapi import HTTPException, Request, status

COOKIE_NAME = "iea_session"

_JWT_SECRET: Optional[str] = None
_JWT_TTL: int = int(os.getenv("JWT_TTL_SECONDS", "604800"))


def _get_secret() -> str:
    global _JWT_SECRET
    if _JWT_SECRET is None:
        _JWT_SECRET = os.getenv("JWT_SECRET")
        if not _JWT_SECRET:
            raise RuntimeError("JWT_SECRET environment variable is not set")
    return _JWT_SECRET


def create_access_token(subject: str) -> str:
    ttl = int(os.getenv("JWT_TTL_SECONDS", str(_JWT_TTL)))
    payload = {
        "sub": subject,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, _get_secret(), algorithms=["HS256"])


def extract_access_token_from_cookie_header(
    cookie_header: str,
) -> Optional[str]:
    """Return the active session JWT from a raw Cookie header."""
    if not cookie_header:
        return None

    try:
        cookies = SimpleCookie()
        cookies.load(cookie_header)
    except CookieError:
        return None

    session_cookie = cookies.get(COOKIE_NAME)
    if session_cookie is None:
        return None

    token = (session_cookie.value or "").strip()
    return token or None


def _decode_header_value(value) -> str:
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return str(value)


def _extract_cookie_header_from_environ(environ: dict) -> str:
    if not isinstance(environ, dict):
        return ""

    cookie_header = environ.get("HTTP_COOKIE")
    if cookie_header:
        return _decode_header_value(cookie_header)

    scope = environ.get("asgi.scope") or environ.get("scope") or {}
    headers = scope.get("headers") if isinstance(scope, dict) else None
    if headers is None:
        headers = environ.get("headers")

    if not headers:
        return ""

    for name, value in headers:
        header_name = _decode_header_value(name).lower()
        if header_name == "cookie":
            return _decode_header_value(value)

    return ""


def validate_access_token_value(token: Optional[str]) -> str:
    """Validate an access token and return its authenticated subject."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    return subject.strip()


def resolve_socket_auth_subject(
    environ: dict,
    auth: Optional[dict] = None,
) -> str:
    """Resolve and validate the subject for a Socket.IO connect."""
    token = None

    if isinstance(auth, dict):
        auth_token = auth.get("token") or auth.get("access_token")
        if isinstance(auth_token, str) and auth_token.strip():
            token = auth_token.strip()

    if token is None:
        cookie_header = _extract_cookie_header_from_environ(environ)
        token = extract_access_token_from_cookie_header(cookie_header)

    return validate_access_token_value(token)


def build_session_cookie_kwargs(request: Request) -> dict:
    ttl_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

    forwarded_proto = (
        request.headers.get("x-forwarded-proto")
        or ""
    ).split(",")[0].strip().lower()

    request_scheme = (request.url.scheme or "").strip().lower()
    base_url = (os.getenv("BASE_URL") or "").strip().lower()
    frontend_url = (os.getenv("FRONTEND_URL") or "").strip().lower()

    is_https = (
        forwarded_proto == "https"
        or request_scheme == "https"
        or base_url.startswith("https://")
        or frontend_url.startswith("https://")
    )

    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "secure": is_https,
        "samesite": "none" if is_https else "lax",
        "max_age": ttl_minutes * 60,
        "path": "/",
    }


def require_jwt_auth(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    try:
        payload = decode_access_token(token)
        return payload.get("sub", "")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
