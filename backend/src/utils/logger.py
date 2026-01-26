"""
Structured JSON Logger

Production-ready logging with JSON output for cloud monitoring tools.
Compatible with CloudWatch, Datadog, and other log aggregators.
"""

import logging
import json
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs as JSON.
    
    Features:
    - ISO8601 timestamps
    - Structured fields (level, message, module, function, line)
    - Exception stack traces
    - Extra fields support
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON string.
        
        Args:
            record: LogRecord to format
            
        Returns:
            JSON string
        """
        log_data: Dict[str, Any] = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get a configured logger with JSON formatting.
    
    Args:
        name: Logger name (usually __name__)
        level: Logging level (default: INFO)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers = []
    
    # Create console handler with JSON formatter
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


# Example usage:
# from src.utils.logger import get_logger
# logger = get_logger(__name__)
# logger.info("User authenticated", extra={'extra_fields': {'user_id': '123', 'email': 'user@example.com'}})
