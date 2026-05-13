"""
P3.5-R4 — Provider Governor Deterministic Tests

Proves the MistralGovernor thread-safety, cooldown behaviour,
interactive-priority logic, and background-worker defer contract.

All tests are purely in-process; no live network, no Mistral API key.

Run with:
    python -m unittest backend.tests.test_provider_governor

from the repository root.
"""

import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.infrastructure.mistral_governor import MistralGovernor  # noqa: E402


# ---------------------------------------------------------------------------
# Section G1 — Basic state and cooldown
# ---------------------------------------------------------------------------

class TestGovernorBasicState(unittest.TestCase):
    """G1x — initial state, cooldown recording, get_cooldown_remaining."""

    def setUp(self):
        self.gov = MistralGovernor()

    # G1-1 — fresh governor has no cooldown and no interactive activity
    def test_fresh_governor_no_cooldown(self):
        self.assertEqual(self.gov.get_cooldown_remaining(), 0.0)
        self.assertFalse(self.gov.is_interactive_active())
        self.assertFalse(self.gov.should_background_defer())

    # G1-2 — record_rate_limit sets a positive cooldown
    def test_record_rate_limit_sets_cooldown(self):
        self.gov.record_rate_limit(retry_after_seconds=10.0)
        remaining = self.gov.get_cooldown_remaining()
        self.assertGreater(remaining, 0.0)
        self.assertLessEqual(remaining, 10.0)

    # G1-3 — cooldown is capped at _MAX_COOLDOWN_SECONDS (60)
    def test_record_rate_limit_capped_at_max(self):
        self.gov.record_rate_limit(retry_after_seconds=9999.0)
        remaining = self.gov.get_cooldown_remaining()
        self.assertLessEqual(remaining, 60.0)

    # G1-4 — record_rate_limit with no argument uses default cooldown
    def test_record_rate_limit_default_fallback(self):
        self.gov.record_rate_limit()
        remaining = self.gov.get_cooldown_remaining()
        # Default is 15 s; remaining must be in (0, 15]
        self.assertGreater(remaining, 0.0)
        self.assertLessEqual(remaining, 15.0)

    # G1-5 — should_background_defer is True while cooldown is active
    def test_should_defer_during_cooldown(self):
        self.gov.record_rate_limit(retry_after_seconds=5.0)
        self.assertTrue(self.gov.should_background_defer())

    # G1-6 — record_rate_limit only ever extends cooldown, never shortens it
    def test_record_rate_limit_does_not_shorten_existing_cooldown(self):
        self.gov.record_rate_limit(retry_after_seconds=30.0)
        before = self.gov.get_cooldown_remaining()
        self.gov.record_rate_limit(retry_after_seconds=1.0)  # shorter
        after = self.gov.get_cooldown_remaining()
        # After the short record, remaining must still be close to the original
        self.assertGreaterEqual(after, before - 0.1)  # tolerate tiny clock drift


# ---------------------------------------------------------------------------
# Section G2 — Interactive-priority tracking
# ---------------------------------------------------------------------------

class TestGovernorInteractivePriority(unittest.TestCase):
    """G2x — begin/end interactive, is_interactive_active, should_background_defer."""

    def setUp(self):
        self.gov = MistralGovernor()

    # G2-1 — begin_interactive increments; is_interactive_active becomes True
    def test_begin_interactive_sets_active(self):
        self.gov.begin_interactive()
        self.assertTrue(self.gov.is_interactive_active())

    # G2-2 — end_interactive after one begin restores inactive state
    def test_end_interactive_restores_inactive(self):
        self.gov.begin_interactive()
        self.gov.end_interactive()
        self.assertFalse(self.gov.is_interactive_active())

    # G2-3 — should_background_defer is True while any interactive call is active
    def test_defer_while_interactive_active(self):
        self.gov.begin_interactive()
        self.assertTrue(self.gov.should_background_defer())

    # G2-4 — multiple concurrent interactive calls; defer clears only after all end
    def test_multiple_concurrent_interactive_calls(self):
        self.gov.begin_interactive()
        self.gov.begin_interactive()
        self.gov.end_interactive()
        # Still one active
        self.assertTrue(self.gov.is_interactive_active())
        self.assertTrue(self.gov.should_background_defer())
        self.gov.end_interactive()
        self.assertFalse(self.gov.is_interactive_active())
        self.assertFalse(self.gov.should_background_defer())

    # G2-5 — end_interactive is bounded at 0 (never goes negative)
    def test_end_interactive_bounded_at_zero(self):
        self.gov.end_interactive()  # extra decrement without prior begin
        self.assertFalse(self.gov.is_interactive_active())
        self.assertEqual(self.gov.get_cooldown_remaining(), 0.0)


# ---------------------------------------------------------------------------
# Section G3 — Thread safety
# ---------------------------------------------------------------------------

class TestGovernorThreadSafety(unittest.TestCase):
    """G3x — concurrent begin/end calls from multiple threads."""

    # G3-1 — parallel begin/end from 50 threads: count returns to 0
    def test_concurrent_begin_end_returns_to_zero(self):
        gov = MistralGovernor()
        errors: list[str] = []
        n = 50

        def _worker():
            try:
                gov.begin_interactive()
                time.sleep(0.001)
                gov.end_interactive()
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=_worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertFalse(gov.is_interactive_active())

    # G3-2 — concurrent record_rate_limit calls: cooldown monotonically extends
    def test_concurrent_record_rate_limit_monotonic(self):
        gov = MistralGovernor()
        results: list[float] = []
        lock = threading.Lock()

        def _worker():
            gov.record_rate_limit(retry_after_seconds=5.0)
            with lock:
                results.append(gov.get_cooldown_remaining())

        threads = [threading.Thread(target=_worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every snapshot should be positive (cooldown was set by at least one call)
        for r in results:
            self.assertGreater(r, 0.0)


# ---------------------------------------------------------------------------
# Section G4 — Background defer (bounded poll)
# ---------------------------------------------------------------------------

class TestGovernorBackgroundDefer(unittest.TestCase):
    """G4x — wait_for_background_slot returns True/False under various conditions."""

    # G4-1 — no cooldown, no interactive → slot granted immediately (True)
    def test_slot_granted_immediately_when_clear(self):
        gov = MistralGovernor()
        result = gov.wait_for_background_slot()
        self.assertTrue(result)

    # G4-2 — cooldown active longer than max defer → slot not granted (False)
    def test_slot_denied_when_cooldown_exceeds_max_defer(self):
        gov = MistralGovernor()
        # Set a cooldown that far exceeds the 30s max defer window
        gov.record_rate_limit(retry_after_seconds=60.0)

        # Patch time so the loop "runs" but max defer is elapsed immediately
        with patch("backend.infrastructure.mistral_governor._BACKGROUND_MAX_DEFER_S", 0.05), \
             patch("backend.infrastructure.mistral_governor._BACKGROUND_POLL_INTERVAL_S", 0.01):
            result = gov.wait_for_background_slot()

        self.assertFalse(result)

    # G4-3 — interactive becomes inactive during poll → slot eventually granted (True)
    def test_slot_granted_when_interactive_clears_mid_poll(self):
        gov = MistralGovernor()
        gov.begin_interactive()

        def _release():
            time.sleep(0.05)
            gov.end_interactive()

        t = threading.Thread(target=_release)
        t.start()

        with patch("backend.infrastructure.mistral_governor._BACKGROUND_MAX_DEFER_S", 2.0), \
             patch("backend.infrastructure.mistral_governor._BACKGROUND_POLL_INTERVAL_S", 0.01):
            result = gov.wait_for_background_slot()

        t.join()
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# Section G5 — get_governor singleton
# ---------------------------------------------------------------------------

class TestGovernorSingleton(unittest.TestCase):
    """G5x — get_governor() always returns the same instance."""

    def test_singleton_identity(self):
        from backend.infrastructure.mistral_governor import get_governor
        g1 = get_governor()
        g2 = get_governor()
        self.assertIs(g1, g2)

    def test_singleton_is_mistral_governor_instance(self):
        from backend.infrastructure.mistral_governor import get_governor
        self.assertIsInstance(get_governor(), MistralGovernor)


if __name__ == "__main__":
    unittest.main()
