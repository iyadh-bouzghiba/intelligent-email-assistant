"""
MistralGovernor — process-local interactive/background traffic coordinator.

On free-tier Render, the API server and background AI worker share the same
process and the same Mistral API quota.  Without coordination, concurrent
background summarization can saturate the provider and cause interactive
translation requests to fail with HTTP 429.

Design:
- Singleton (_GOVERNOR module-level instance) — import get_governor() everywhere.
- Thread-safe: uses threading.Lock for all state mutations.
- Interactive-priority: translate-render route signals "interactive active"
  before each Mistral call; background worker checks this and backs off.
- Cooldown: a 429 event from either path sets a cooldown timestamp.  Both
  paths respect it before making new calls.
- Conservative: cooldown is bounded (max _MAX_COOLDOWN_SECONDS).  Backoff
  delays are bounded and never loop forever.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_COOLDOWN_SECONDS = 60        # hard cap on provider cooldown after 429
_DEFAULT_COOLDOWN_SECONDS = 15   # fallback when no Retry-After header provided
_BACKGROUND_POLL_INTERVAL_S = 2.0  # how often background checks for a slot
_BACKGROUND_MAX_DEFER_S = 30.0    # max time background waits before giving up


class MistralGovernor:
    """
    Single process-local coordinator for Mistral API traffic.

    Shared between the async translate-render route (FastAPI event-loop thread)
    and the synchronous AI summarizer worker (background daemon thread) via the
    module-level singleton.  All state mutations are protected by threading.Lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._interactive_count: int = 0   # in-flight interactive calls
        self._cooldown_until: float = 0.0  # monotonic end of provider cooldown

    # ------------------------------------------------------------------
    # Interactive path (translate-render route)
    # ------------------------------------------------------------------

    def begin_interactive(self) -> None:
        """Signal that an interactive translation call is starting."""
        with self._lock:
            self._interactive_count += 1
        logger.info("[GOVERNOR] interactive_begin count=%d", self._interactive_count)

    def end_interactive(self) -> None:
        """Signal that an interactive translation call has completed."""
        with self._lock:
            self._interactive_count = max(0, self._interactive_count - 1)
        logger.info("[GOVERNOR] interactive_end count=%d", self._interactive_count)

    # ------------------------------------------------------------------
    # Provider rate-limit recording (shared across both paths)
    # ------------------------------------------------------------------

    def record_rate_limit(self, retry_after_seconds: Optional[float] = None) -> None:
        """
        Record a provider 429 / rate-limit event and extend the cooldown window.

        Uses retry_after_seconds when provided by the Retry-After header.
        Falls back to _DEFAULT_COOLDOWN_SECONDS otherwise.
        Always capped at _MAX_COOLDOWN_SECONDS so cooldown is bounded.
        Only extends the cooldown — never shortens an already-longer cooldown.
        """
        raw = retry_after_seconds if retry_after_seconds is not None else _DEFAULT_COOLDOWN_SECONDS
        clamped = min(float(raw), float(_MAX_COOLDOWN_SECONDS))
        with self._lock:
            new_until = time.monotonic() + clamped
            if new_until > self._cooldown_until:
                self._cooldown_until = new_until
        logger.warning(
            "[GOVERNOR] rate_limit_recorded cooldown_s=%.1f remaining=%.1f",
            clamped,
            self.get_cooldown_remaining(),
        )

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_cooldown_remaining(self) -> float:
        """Return remaining cooldown seconds (0.0 if no active cooldown)."""
        with self._lock:
            return max(0.0, self._cooldown_until - time.monotonic())

    def is_interactive_active(self) -> bool:
        """True when at least one interactive translation call is in-flight."""
        with self._lock:
            return self._interactive_count > 0

    def should_background_defer(self) -> bool:
        """
        Return True when background AI calls should yield.

        Two conditions trigger deferral (either is sufficient):
          1. An interactive translation call is currently in-flight.
          2. A provider cooldown is active (from a recent 429 event).

        Background callers should poll this in a bounded loop (see
        wait_for_background_slot) before each Mistral call.
        """
        with self._lock:
            if self._interactive_count > 0:
                return True
            if time.monotonic() < self._cooldown_until:
                return True
            return False

    # ------------------------------------------------------------------
    # Background helper — blocking poll with bounded timeout
    # ------------------------------------------------------------------

    def wait_for_background_slot(self) -> bool:
        """
        Block (up to _BACKGROUND_MAX_DEFER_S) until the governor allows
        background traffic.

        Returns True when a slot is granted within the deadline.
        Returns False when still deferred at deadline expiry — caller should
        skip the current job cycle and retry in the next batch.

        Called from the synchronous background worker thread before each
        Mistral API call (outside the concurrency semaphore so the slot is
        not held during the wait).
        """
        deadline = time.monotonic() + _BACKGROUND_MAX_DEFER_S
        while time.monotonic() < deadline:
            if not self.should_background_defer():
                return True
            logger.info(
                "[GOVERNOR] background_deferred interactive=%s cooldown_remaining=%.1fs",
                self.is_interactive_active(),
                self.get_cooldown_remaining(),
            )
            time.sleep(_BACKGROUND_POLL_INTERVAL_S)
        logger.warning(
            "[GOVERNOR] background_defer_timeout max_wait=%.1fs — skipping slot",
            _BACKGROUND_MAX_DEFER_S,
        )
        return False


# Process-level singleton — import via get_governor() everywhere.
_GOVERNOR = MistralGovernor()


def get_governor() -> MistralGovernor:
    """Return the process-level governor singleton."""
    return _GOVERNOR
