"""
Configuration Management with Environment Validation

This module provides centralized configuration with strict validation
to prevent silent failures in production.
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Application configuration with environment validation.
    Fails fast if critical variables are missing.
    """
    
    # OAuth2 - REQUIRED for production
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback/google")
    
    # JWT - REQUIRED for authentication
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DAYS: int = 7
    
    # Mistral AI
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # Redis (for WebSocket scaling)
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

    # Google Cloud Pub/Sub - REQUIRED for event-driven ingestion
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
    PUBSUB_TOPIC_ID: str = os.getenv("PUBSUB_TOPIC_ID", "")
    PUBSUB_SUBSCRIPTION_ID: str = os.getenv("PUBSUB_SUBSCRIPTION_ID", "")
    
    @classmethod
    def validate(cls) -> None:
        """
        Validate critical environment variables at startup.
        Raises RuntimeError if any required variables are missing.
        
        This prevents silent failures in production where the app
        starts but OAuth/JWT don't work.
        """
        missing = []
        warnings = []
        
        # Critical variables (app won't work without these)
        if not cls.JWT_SECRET_KEY:
            missing.append("JWT_SECRET_KEY")
        
        # In production, Pub/Sub is required for ingestion
        if cls.is_production():
            if not cls.GCP_PROJECT_ID:
                missing.append("GCP_PROJECT_ID")
            if not cls.PUBSUB_TOPIC_ID:
                missing.append("PUBSUB_TOPIC_ID")
            if not cls.PUBSUB_SUBSCRIPTION_ID:
                missing.append("PUBSUB_SUBSCRIPTION_ID")

        # OAuth variables (warn if missing, but allow demo mode)
        if not cls.GOOGLE_CLIENT_ID:
            warnings.append("GOOGLE_CLIENT_ID (OAuth will not work)")
        if not cls.GOOGLE_CLIENT_SECRET:
            warnings.append("GOOGLE_CLIENT_SECRET (OAuth will not work)")
        
        # Pub/Sub in development is optional
        if not cls.is_production():
            if not cls.GCP_PROJECT_ID:
                warnings.append("GCP_PROJECT_ID (Pub/Sub ingestion disabled)")
            if not cls.PUBSUB_TOPIC_ID:
                warnings.append("PUBSUB_TOPIC_ID (Pub/Sub ingestion disabled)")
            if not cls.PUBSUB_SUBSCRIPTION_ID:
                warnings.append("PUBSUB_SUBSCRIPTION_ID (Pub/Sub ingestion disabled)")

        # Mistral AI (warn if missing, demo mode available)
        if not cls.MISTRAL_API_KEY:
            warnings.append("MISTRAL_API_KEY (AI features will run in demo mode)")
        
        if missing:
            raise RuntimeError(
                f"\n{'='*70}\n"
                f"CRITICAL ERROR: Missing required environment variables:\n"
                f"{chr(10).join('  - ' + var for var in missing)}\n\n"
                f"Add these to your .env file or configure a secrets manager.\n"
                f"{'='*70}\n"
            )
        
        if warnings:
            print(
                f"\n{'='*70}\n"
                f"⚠️  WARNING: Optional environment variables not set:\n"
                f"{chr(10).join('  - ' + var for var in warnings)}\n"
                f"Some features may be limited.\n"
                f"{'='*70}\n"
            )
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production environment."""
        return cls.ENVIRONMENT.lower() == "production"
    
    @classmethod
    def get_callback_url(cls) -> str:
        """
        Get canonical OAuth callback URL based on environment.
        
        CANONICAL PATTERN: /auth/callback/google
        
        PRODUCTION:
            Value read from GOOGLE_REDIRECT_URI environment variable.
            Example: https://your-app.onrender.com/auth/callback/google
            
        LOCAL/DEVELOPMENT:
            Defaults to http://localhost:8000/auth/callback/google
        """
        if cls.is_production():
            # In production, use the configured redirect URI from environment
            # This is critical for Render deployments.
            return cls.GOOGLE_REDIRECT_URI
        else:
            # In development, always use the canonical localhost path on port 8000
            return "http://localhost:8000/auth/callback/google"


# Validate configuration on module import
# This ensures the app fails immediately if misconfigured
try:
    Config.validate()
    print("✅ Configuration validated successfully")
except RuntimeError as e:
    print(str(e))
    # In production, we want to fail hard
    # In development, we can continue with warnings
    if Config.is_production():
        raise
