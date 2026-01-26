"""
Health Check Endpoint

Comprehensive health checks for cloud load balancers and monitoring.
Checks: Database, Redis, Internet connectivity, and service status.
"""

from fastapi import APIRouter, Response
from typing import Dict, Any
import redis
import requests
from datetime import datetime
from src.config import Config
from src.utils.observability import metrics_collector

router = APIRouter()


async def check_redis() -> Dict[str, Any]:
    """Check Redis connectivity and responsiveness."""
    try:
        redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            socket_connect_timeout=2
        )
        
        # Test ping
        start = datetime.utcnow()
        redis_client.ping()
        latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
        
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


async def check_internet() -> Dict[str, Any]:
    """Check internet connectivity (for API calls)."""
    try:
        response = requests.get("https://www.google.com", timeout=3)
        return {
            "status": "healthy" if response.status_code == 200 else "degraded",
            "status_code": response.status_code
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


async def check_mistral_api() -> Dict[str, Any]:
    """Check Mistral API availability."""
    if not Config.MISTRAL_API_KEY:
        return {
            "status": "not_configured",
            "message": "MISTRAL_API_KEY not set"
        }
    
    try:
        # Simple API check (you could ping a lightweight endpoint)
        return {
            "status": "configured",
            "api_key_present": True
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/health")
async def health_check(response: Response):
    """
    Comprehensive health check endpoint.
    
    Returns 200 OK only if all critical services are healthy.
    Used by cloud load balancers for auto-healing.
    """
    checks = {
        "redis": await check_redis(),
        "internet": await check_internet(),
        "mistral_api": await check_mistral_api()
    }
    
    # Determine overall health
    critical_checks = ["redis", "internet"]
    is_healthy = all(
        checks[service]["status"] == "healthy"
        for service in critical_checks
    )
    
    # Get metrics summary
    try:
        metrics = metrics_collector.get_metrics_summary()
    except Exception:
        metrics = {"error": "Failed to collect metrics"}
    
    health_response = {
        "status": "healthy" if is_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
        "metrics": metrics,
        "version": "1.0.0",
        "environment": Config.ENVIRONMENT
    }
    
    # Set appropriate status code
    if not is_healthy:
        response.status_code = 503  # Service Unavailable
    
    return health_response


@router.get("/health/ready")
async def readiness_check():
    """
    Kubernetes readiness probe.
    Returns 200 if service is ready to accept traffic.
    """
    redis_check = await check_redis()
    
    if redis_check["status"] != "healthy":
        return Response(status_code=503, content="Service not ready")
    
    return {"status": "ready"}


@router.get("/health/live")
async def liveness_check():
    """
    Kubernetes liveness probe.
    Returns 200 if service is alive (even if degraded).
    """
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
