import os
import time


class AIState:
    """
    AI Graceful Degradation State Machine.
    Class-variable singleton — never instantiated.
    States: ACTIVE | DEGRADED | DISABLED
    """

    # --------------- States ------------------------------------------------
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"

    # --------------- Configuration -----------------------------------------
    TTL_SECONDS = 120
    DEGRADED_DWELL_SECONDS = 300

    # --------------- Internal state ----------------------------------------
    _state = None
    _last_checked = 0.0
    _degraded_since = 0.0
    _last_logged_state = None
    _initialized = False

    # --------------- Initialization ----------------------------------------
    @classmethod
    def _initialize(cls):
        """Runs exactly once on first access.  Order is strict and locked."""
        if cls._initialized:
            return
        cls._initialized = True
        now = time.time()
        cls._last_checked = now

        # 1. AI_ENABLED=false  →  DISABLED (precedence-absolute, terminal)
        if os.getenv("AI_ENABLED", "").lower() == "false":
            cls._state = cls.DISABLED
            cls._degraded_since = 0.0
            cls._emit("AI explicitly disabled via AI_ENABLED=false")
            return

        # 2. MISTRAL_API_KEY missing or empty  →  DEGRADED
        if not os.getenv("MISTRAL_API_KEY", "").strip():
            cls._state = cls.DEGRADED
            cls._degraded_since = now
            cls._emit("AI key missing — demo mode active")
            return

        # 3. Key present  →  ACTIVE (tentative)
        cls._state = cls.ACTIVE
        cls._degraded_since = 0.0
        cls._emit("AI key detected — AI active (unconfirmed)")

    # --------------- Logging -----------------------------------------------
    @classmethod
    def _emit(cls, message: str):
        """Prints once per state.  Repeated logs for the same state are suppressed."""
        if cls._last_logged_state != cls._state:
            print(f"[AI_STATE] {message}")
            cls._last_logged_state = cls._state

    # --------------- Public API --------------------------------------------
    @classmethod
    def state(cls) -> str:
        """Returns current state.  Performs TTL re-check if needed.  Never raises."""
        try:
            if not cls._initialized:
                cls._initialize()
            cls.maybe_recheck()
            return cls._state
        except Exception:
            return cls._state if cls._state else cls.DEGRADED

    @classmethod
    def maybe_recheck(cls):
        """
        TTL-gated env recheck.  Called internally by state().
        Never performs network calls.
        Honors TTL gate and DEGRADED dwell anti-oscillation rules.
        """
        if not cls._initialized:
            return

        # DISABLED is terminal — no recheck ever
        if cls._state == cls.DISABLED:
            return

        now = time.time()

        # TTL gate: skip if interval has not elapsed
        if now - cls._last_checked < cls.TTL_SECONDS:
            return
        cls._last_checked = now

        # AI_ENABLED=false is precedence-absolute at any point in time
        if os.getenv("AI_ENABLED", "").lower() == "false":
            cls._state = cls.DISABLED
            cls._degraded_since = 0.0
            cls._emit("AI explicitly disabled via AI_ENABLED=false")
            return

        key = os.getenv("MISTRAL_API_KEY", "").strip()

        if cls._state == cls.DEGRADED:
            # Anti-oscillation: DEGRADED → ACTIVE requires TTL elapsed (already
            # gated above) AND dwell elapsed AND key present.
            if not key:
                return  # stay DEGRADED — key still missing
            if (now - cls._degraded_since) < cls.DEGRADED_DWELL_SECONDS:
                return  # stay DEGRADED — dwell not yet satisfied
            # Both conditions met: promote to ACTIVE
            cls._state = cls.ACTIVE
            cls._degraded_since = 0.0
            cls._emit("AI key restored after dwell period — AI active")
            return

        if cls._state == cls.ACTIVE:
            # Key disappeared while ACTIVE → immediate DEGRADED
            if not key:
                cls._state = cls.DEGRADED
                cls._degraded_since = now
                cls._emit("AI key missing — demo mode active")

    @classmethod
    def transition_to_degraded(cls, reason: str):
        """
        Explicit degradation trigger (e.g. provider exception).
        Sets dwell timer.  Logs once per transition.  Never raises.
        """
        try:
            if not cls._initialized:
                cls._initialize()
            # DISABLED is terminal — never leave it
            if cls._state == cls.DISABLED:
                return
            # Only transition if not already DEGRADED (avoids resetting dwell timer)
            if cls._state != cls.DEGRADED:
                cls._state = cls.DEGRADED
                cls._degraded_since = time.time()
                cls._emit(f"AI degraded: {reason}")
        except Exception:
            pass  # contract: never raises
