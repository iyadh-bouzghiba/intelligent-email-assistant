"""
Redis-Based Rate Limiting Middleware

Implements sliding window counter algorithm for:
- Global API protection (DoS prevention)
- Per-user limits (cost management for Mistral AI)
- Graceful 429 responses with Retry-After headers
"""

import redis
import time
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from src.config import Config


class RateLimiter:
    """
    Redis-based rate limiter with sliding window algorithm.
    
    Features:
    - Global and per-user limits
    - Atomic Redis operations
    - Retry-After header calculation
    - Cost-aware limiting (different costs for different endpoints)
    """
    
    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5
        )
    
    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        cost: int = 1
    ) -> tuple[bool, Optional[int]]:
        """
        Check if request is within rate limit using sliding window.
        
        Args:
            key: Redis key (e.g., "global" or "user:123")
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
            cost: Cost of this request (default 1, AI calls might be 5)
            
        Returns:
            Tuple of (allowed: bool, retry_after: Optional[int])
        """
        now = time.time()
        window_start = now - window_seconds
        
        # Redis key for this rate limit
        redis_key = f"rate_limit:{key}"
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = self.redis_client.pipeline()
            
            # Remove old entries outside the window
            pipe.zremrangebyscore(redis_key, 0, window_start)
            
            # Count current requests in window
            pipe.zcard(redis_key)
            
            # Execute pipeline
            results = pipe.execute()
            current_count = results[1]
            
            # Check if adding this request would exceed limit
            if current_count + cost > max_requests:
                # Calculate retry_after
                # Get the oldest request timestamp
                oldest = self.redis_client.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    oldest_timestamp = oldest[0][1]
                    retry_after = int(oldest_timestamp + window_seconds - now) + 1
                else:
                    retry_after = window_seconds
                
                return False, retry_after
            
            # Add current request to sorted set
            self.redis_client.zadd(redis_key, {str(now): now})
            
            # Set expiration on the key
            self.redis_client.expire(redis_key, window_seconds)
            
            return True, None
            
        except redis.RedisError as e:
            # If Redis is down, allow the request (fail open)
            # Log this error in production
            print(f"[Rate Limiter] Redis error: {e}")
            return True, None
    
    def get_user_key(self, request: Request) -> str:
        """
        Extract user identifier from request.
        
        Priority:
        1. JWT user_id from cookie
        2. IP address (fallback)
        """
        # Try to get user_id from JWT cookie
        from src.auth.jwt_service import JWTService
        
        auth_token = request.cookies.get("auth_token")
        if auth_token:
            user_id = JWTService.extract_user_id(auth_token)
            if user_id:
                return f"user:{user_id}"
        
        # Fallback to IP address
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"


# Global rate limiter instance
rate_limiter = RateLimiter()


async def rate_limit_middleware(request: Request, call_next):
    """
    FastAPI middleware for rate limiting.
    
    Limits:
    - Global: 1000 requests per minute (DoS protection)
    - Per-user: 50 AI requests per hour (cost management)
    """
    
    # Check global rate limit
    allowed, retry_after = rate_limiter.check_rate_limit(
        key="global",
        max_requests=1000,
        window_seconds=60
    )
    
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too many requests globally. Please try again later.",
                "retry_after": retry_after
            },
            headers={"Retry-After": str(retry_after)}
        )
    
    # Check per-user rate limit for AI endpoints
    if "/analyze" in request.url.path or "/draft" in request.url.path:
        user_key = rate_limiter.get_user_key(request)
        
        # AI calls have higher cost (5x)
        allowed, retry_after = rate_limiter.check_rate_limit(
            key=user_key,
            max_requests=50,
            window_seconds=3600,  # 1 hour
            cost=5
        )
        
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "You've reached your AI analysis limit. Please wait before trying again.",
                    "retry_after": retry_after,
                    "limit": "50 AI requests per hour"
                },
                headers={"Retry-After": str(retry_after)}
            )
    
    # Request is allowed
    response = await call_next(request)
    return response
