"""
JWT Authentication Service

Provides secure token creation and verification for user authentication.
Tokens are designed to be stored in HttpOnly cookies, not LocalStorage.
"""

import jwt
from datetime import datetime, timedelta
from typing import Dict, Optional
from src.config import Config


class JWTService:
    """
    Service for creating and verifying JWT tokens.
    
    Security features:
    - HS256 algorithm
    - 7-day expiration
    - Issued-at timestamp
    - User ID and email in payload
    """
    
    @staticmethod
    def create_token(user_id: str, email: str) -> str:
        """
        Create a secure JWT token for authenticated user.
        
        Args:
            user_id: Unique user identifier
            email: User's email address
            
        Returns:
            Encoded JWT token string
        """
        payload = {
            'user_id': user_id,
            'email': email,
            'exp': datetime.utcnow() + timedelta(days=Config.JWT_EXPIRATION_DAYS),
            'iat': datetime.utcnow()
        }
        
        return jwt.encode(
            payload,
            Config.JWT_SECRET_KEY,
            algorithm=Config.JWT_ALGORITHM
        )
    
    @staticmethod
    def verify_token(token: str) -> Optional[Dict]:
        """
        Verify and decode a JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded payload dict if valid, None if invalid/expired
        """
        try:
            payload = jwt.decode(
                token,
                Config.JWT_SECRET_KEY,
                algorithms=[Config.JWT_ALGORITHM]
            )
            return payload
        except jwt.ExpiredSignatureError:
            # Token has expired
            return None
        except jwt.InvalidTokenError:
            # Token is invalid (tampered, malformed, etc.)
            return None
    
    @staticmethod
    def extract_user_id(token: str) -> Optional[str]:
        """
        Extract user_id from token without full verification.
        Useful for quick lookups.
        
        Args:
            token: JWT token string
            
        Returns:
            User ID if token is valid, None otherwise
        """
        payload = JWTService.verify_token(token)
        return payload.get('user_id') if payload else None
