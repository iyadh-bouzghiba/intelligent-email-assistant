"""
Graceful Shutdown Handler

Implements clean shutdown for Docker/Kubernetes SIGTERM signals.
Ensures all connections are closed properly before exit.
"""

import signal
import sys
import asyncio
from typing import Callable, List
from src.utils.observability import get_logger

logger = get_logger(__name__)


class GracefulShutdown:
    """
    Handles graceful shutdown of the application.
    
    Features:
    - SIGTERM/SIGINT signal handling
    - Cleanup callback registration
    - Timeout enforcement
    - Logging
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize graceful shutdown handler.
        
        Args:
            timeout: Maximum seconds to wait for cleanup
        """
        self.timeout = timeout
        self.cleanup_callbacks: List[Callable] = []
        self.shutdown_initiated = False
    
    def register_cleanup(self, callback: Callable):
        """
        Register a cleanup callback to run on shutdown.
        
        Args:
            callback: Async or sync function to call during shutdown
        """
        self.cleanup_callbacks.append(callback)
    
    async def _run_cleanup(self):
        """Run all registered cleanup callbacks."""
        logger.info("Starting graceful shutdown", callback_count=len(self.cleanup_callbacks))
        
        for callback in self.cleanup_callbacks:
            try:
                logger.info(f"Running cleanup: {callback.__name__}")
                
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
                    
                logger.info(f"Cleanup completed: {callback.__name__}")
            except Exception as e:
                logger.error(f"Cleanup failed: {callback.__name__}", error=e)
        
        logger.info("Graceful shutdown complete")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        if self.shutdown_initiated:
            logger.warning("Shutdown already in progress, forcing exit")
            sys.exit(1)
        
        self.shutdown_initiated = True
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown")
        
        # Run cleanup with timeout
        try:
            asyncio.run(
                asyncio.wait_for(
                    self._run_cleanup(),
                    timeout=self.timeout
                )
            )
        except asyncio.TimeoutError:
            logger.error(f"Shutdown timeout after {self.timeout}s, forcing exit")
        except Exception as e:
            logger.error("Shutdown error", error=e)
        finally:
            sys.exit(0)
    
    def setup(self):
        """Setup signal handlers."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        logger.info("Graceful shutdown handler registered")


# Global shutdown handler
shutdown_handler = GracefulShutdown()


# Example cleanup functions
async def close_redis_connections():
    """Close Redis connections."""
    from src.middleware.rate_limiter import rate_limiter
    from src.services.token_refresh import token_refresh_service
    
    try:
        rate_limiter.redis_client.close()
        token_refresh_service.redis_client.close()
        logger.info("Redis connections closed")
    except Exception as e:
        logger.error("Failed to close Redis connections", error=e)


async def save_application_state():
    """Save application state before shutdown."""
    try:
        from src.data.store import PersistenceManager
        # Trigger final save
        logger.info("Saving application state")
        # persistence.save(...) would go here
    except Exception as e:
        logger.error("Failed to save application state", error=e)


# Register cleanup callbacks
shutdown_handler.register_cleanup(close_redis_connections)
shutdown_handler.register_cleanup(save_application_state)
