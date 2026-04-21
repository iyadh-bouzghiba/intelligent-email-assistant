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


def _is_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.lower() == "https"
    return request.url.scheme == "https"


def build_session_cookie_kwargs(request: Request) -> dict:
    ttl = int(os.getenv("JWT_TTL_SECONDS", str(_JWT_TTL)))
    secure = _is_secure(request)
    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "secure": secure,
        "samesite": "none" if secure else "lax",
        "max_age": ttl,
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
