import os
import time
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
