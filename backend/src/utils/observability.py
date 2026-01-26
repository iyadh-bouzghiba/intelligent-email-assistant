"""
Enterprise Observability Configuration

Implements structured logging, metrics tracking, and health checks for
production monitoring with Datadog, ELK, CloudWatch, etc.
"""

import logging
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional
from contextlib import contextmanager
import redis
from src.config import Config


class MetricsCollector:
    """
    Collects and tracks application metrics.
    
    Metrics tracked:
    - Mistral AI latency
    - Gmail API error rates
    - Rate limit hits
    - Token refresh events
    """
    
    def __init__(self):
        """Initialize metrics storage in Redis."""
        self.redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            decode_responses=True
        )
    
    def record_mistral_latency(self, latency_ms: float, model: str):
        """Record Mistral AI API latency."""
        key = f"metrics:mistral_latency:{model}"
        self.redis_client.lpush(key, latency_ms)
        self.redis_client.ltrim(key, 0, 999)  # Keep last 1000
        self.redis_client.expire(key, 3600)  # 1 hour TTL
    
    def record_gmail_error(self, status_code: int):
        """Record Gmail API error."""
        key = f"metrics:gmail_errors:{status_code}"
        self.redis_client.incr(key)
        self.redis_client.expire(key, 3600)
    
    def record_rate_limit_hit(self, limit_type: str):
        """Record rate limit hit."""
        key = f"metrics:rate_limit_hits:{limit_type}"
        self.redis_client.incr(key)
        self.redis_client.expire(key, 3600)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics."""
        # Get Mistral latencies
        mistral_keys = self.redis_client.keys("metrics:mistral_latency:*")
        mistral_latencies = {}
        for key in mistral_keys:
            model = key.split(":")[-1]
            latencies = [float(x) for x in self.redis_client.lrange(key, 0, -1)]
            if latencies:
                mistral_latencies[model] = {
                    "avg_ms": sum(latencies) / len(latencies),
                    "max_ms": max(latencies),
                    "min_ms": min(latencies),
                    "count": len(latencies)
                }
        
        # Get error counts
        error_keys = self.redis_client.keys("metrics:gmail_errors:*")
        gmail_errors = {}
        for key in error_keys:
            status_code = key.split(":")[-1]
            count = int(self.redis_client.get(key) or 0)
            gmail_errors[status_code] = count
        
        # Get rate limit hits
        rate_limit_keys = self.redis_client.keys("metrics:rate_limit_hits:*")
        rate_limit_hits = {}
        for key in rate_limit_keys:
            limit_type = key.split(":")[-1]
            count = int(self.redis_client.get(key) or 0)
            rate_limit_hits[limit_type] = count
        
        return {
            "mistral_latencies": mistral_latencies,
            "gmail_errors": gmail_errors,
            "rate_limit_hits": rate_limit_hits,
            "timestamp": datetime.utcnow().isoformat()
        }


class StructuredLogger:
    """
    Structured logger with JSON output and context tracking.
    
    Features:
    - JSON formatted logs
    - Request ID tracking
    - Performance timing
    - Error context
    """
    
    def __init__(self, name: str):
        """Initialize logger with JSON formatter."""
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Add JSON handler
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        self.logger.addHandler(handler)
        
        self.logger.propagate = False
    
    def info(self, message: str, **kwargs):
        """Log info message with context."""
        self.logger.info(message, extra={'context': kwargs})
    
    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """Log error message with exception details."""
        context = kwargs.copy()
        if error:
            context['error_type'] = type(error).__name__
            context['error_message'] = str(error)
        self.logger.error(message, extra={'context': context}, exc_info=error)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with context."""
        self.logger.warning(message, extra={'context': kwargs})
    
    @contextmanager
    def timer(self, operation: str):
        """
        Context manager for timing operations.
        
        Usage:
            with logger.timer("mistral_api_call"):
                result = await mistral.generate(...)
        """
        start = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - start) * 1000
            self.info(f"{operation}_completed", duration_ms=duration_ms)


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add context if present
        if hasattr(record, 'context'):
            log_data['context'] = record.context
        
        # Add exception if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


# Global instances
metrics_collector = MetricsCollector()


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)
