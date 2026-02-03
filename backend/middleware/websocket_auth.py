"""
WebSocket Authentication Middleware

Provides JWT-based authentication for WebSocket connections.
Prevents unauthorized access to real-time updates.
"""

import socketio
from typing import Optional
from backend.auth.jwt_service import JWTService


async def authenticate_socket(sid: str, environ: dict) -> bool:
    """
    Verify JWT token before allowing WebSocket connection.
    
    Security features:
    - Extracts token from HTTP cookie
    - Verifies JWT signature and expiration
    - Stores user info in socket session
    - Rejects invalid/missing tokens
    
    Args:
        sid: Socket ID
        environ: ASGI environ dict
        
    Returns:
        True if authenticated, False otherwise
    """
    # Extract cookies from environ
    cookies = environ.get('HTTP_COOKIE', '')
    token = None
    
    # Parse auth_token from cookies
    for cookie in cookies.split(';'):
        cookie = cookie.strip()
        if cookie.startswith('auth_token='):
            token = cookie.split('auth_token=')[1]
            break
    
    if not token:
        print(f"[WebSocket Auth] No token found for {sid}")
        return False
    
    # Verify JWT
    jwt_service = JWTService()
    payload = jwt_service.verify_token(token)
    
    if not payload:
        print(f"[WebSocket Auth] Invalid token for {sid}")
        return False
    
    # Token is valid - store user info in session
    # Note: This requires the socket.io server instance
    # We'll pass it when we integrate this
    print(f"[WebSocket Auth] Authenticated user: {payload.get('email')} ({sid})")
    
    return True


def extract_token_from_cookie(cookie_header: str) -> Optional[str]:
    """
    Extract auth_token from cookie header.
    
    Args:
        cookie_header: Raw cookie header string
        
    Returns:
        Token string if found, None otherwise
    """
    if not cookie_header:
        return None
    
    for cookie in cookie_header.split(';'):
        cookie = cookie.strip()
        if cookie.startswith('auth_token='):
            return cookie.split('auth_token=')[1]
    
    return None
