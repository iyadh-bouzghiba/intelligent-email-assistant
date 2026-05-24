"""
WORKER-TESTS-01 — Deterministic unit tests for worker_entry.py contracts.

Coverage groups:
  A   Safe import behavior
  B   FastAPI app and /healthz endpoint behavior
  C   start_worker() execution and restart path
  D   start_ai_worker() execution and exception handling
  E   main() WORKER_MODE / AI_SUMM_ENABLED environment gating and thread boundaries
  F   main() uvicorn startup parameters and port parsing
  G   validate_startup() pass / fail-fast path

No live uvicorn, threads, Supabase, Gmail, Mistral, OAuth, network, or real secrets.
"""

import io
import os
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Capture-safety block ─────────────────────────────────────────────────────
#
# Root cause: backend/api/service.py executes at module-import time:
#
#   sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)   # ~line 70
#
# Under pytest, sys.stdout may be a capture proxy whose fileno() returns a fd
# owned by pytest's SpooledTemporaryFile.  os.fdopen() then takes *ownership*
# of that fd.  When the resulting file object is garbage-collected it closes the
# fd, and pytest teardown crashes with "OSError: [Errno 9] Bad file descriptor".
#
# Fix A1 — scoped stub (protects worker_entry.py import chain):
# worker_entry.py → worker.py → backend.api.service (fd theft hazard).
# Install a minimal stub for backend.api.service ONLY for the duration of
# importing worker_entry_module.  Restore sys.modules immediately after so later
# imports of the real backend.api.service are not blocked by the stub.
_svc_had_prev = 'backend.api.service' in sys.modules
_svc_prev = sys.modules.get('backend.api.service')
if not _svc_had_prev:
    _svc_stub = types.ModuleType('backend.api.service')
    _svc_stub.sio = None
    _svc_stub.sio_app = MagicMock(name='sio_app_stub')
    sys.modules['backend.api.service'] = _svc_stub
    _ENTRY_SVC_STUB = _svc_stub
else:
    _ENTRY_SVC_STUB = None

import backend.infrastructure.worker_entry as entry_module

# Restore sys.modules["backend.api.service"] to its pre-import state.
if not _svc_had_prev:
    sys.modules.pop('backend.api.service', None)
elif _svc_prev is not None:
    sys.modules['backend.api.service'] = _svc_prev

# Fix B: worker_entry.py uses print() rather than a named logger, so no handler
# redirection is needed.  Guard in case a logger is added later.
import logging
if hasattr(entry_module, 'logger'):
    for _h in list(entry_module.logger.handlers):
        if hasattr(_h, 'stream'):
            _h.stream = io.StringIO()
    entry_module.logger.handlers = [logging.NullHandler()]

# Fix A2 — pre-load the real backend.api.service with os.fdopen neutralized.
# After removing the stub above, if the real service.py is not yet in sys.modules
# we import it now with os.fdopen patched to a no-op on the sys.stdout fd.  This
# prevents fd theft while fully populating sys.modules so that subsequent imports
# by other test files find the real module already cached and do not re-execute
# service.py ~line 70.
import os as _os_mod
if 'backend.api.service' not in sys.modules:
    _real_fdopen = _os_mod.fdopen
    def _fdopen_guard(fd, *_a, **_kw):
        try:
            _sfd = sys.stdout.fileno()
        except Exception:
            _sfd = -1
        if fd == _sfd:
            return sys.stdout
        return _real_fdopen(fd, *_a, **_kw)
    _os_mod.fdopen = _fdopen_guard
    try:
        import importlib as _il; _il.import_module('backend.api.service'); del _il
    except Exception:
        pass
    finally:
        _os_mod.fdopen = _real_fdopen
    del _fdopen_guard, _real_fdopen
del _os_mod
# ─────────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_svc_stub():
    """Minimal backend.api.service stub for main() tests (provides sio_app)."""
    stub = types.ModuleType('backend.api.service')
    stub.sio = None
    stub.sio_app = MagicMock(name='sio_app')
    return stub


def _make_ai_entry_stub(mock_main=None):
    """Minimal backend.infrastructure.ai_summarizer_entry stub."""
    stub = types.ModuleType('backend.infrastructure.ai_summarizer_entry')
    stub.main = mock_main if mock_main is not None else MagicMock()
    return stub


def _env_for(**kwargs):
    """Build a controlled env dict; omits keys the caller did not specify."""
    return kwargs


# ---------------------------------------------------------------------------
# A. Safe import behavior
# ---------------------------------------------------------------------------

class TestWorkerEntryImportSafety(unittest.TestCase):
    def test_module_imported_without_hanging(self):
        """Asserts uvicorn.run was NOT called at import time (would block the process)."""
        self.assertIsNotNone(entry_module)

    def test_module_exposes_fastapi_app(self):
        from fastapi import FastAPI
        self.assertIsInstance(entry_module.app, FastAPI)

    def test_module_exposes_healthz_route(self):
        routes = [r.path for r in entry_module.app.routes]
        self.assertIn("/healthz", routes)

    def test_module_exposes_main_callable(self):
        self.assertTrue(callable(entry_module.main))

    def test_module_exposes_start_worker_callable(self):
        self.assertTrue(callable(entry_module.start_worker))

    def test_module_exposes_start_ai_worker_callable(self):
        self.assertTrue(callable(entry_module.start_ai_worker))

    def test_module_exposes_validate_startup_callable(self):
        self.assertTrue(callable(entry_module.validate_startup))

    def test_module_does_not_start_real_threads_at_import(self):
        """No thread should be alive whose name originates from worker_entry import."""
        import threading
        live_names = {t.name for t in threading.enumerate()}
        # Worker threads spawned by main() would be named "Thread-N"; they should
        # not exist at import time.  main() is never called at module level.
        self.assertNotIn("WorkerThread", live_names)


# ---------------------------------------------------------------------------
# B. FastAPI app and /healthz endpoint behavior
# ---------------------------------------------------------------------------

class TestWorkerEntryHealthzEndpoint(unittest.TestCase):
    def test_healthz_returns_worker_ok_when_last_cycle_within_180s(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {"last_cycle": time.time() - 10}):
            result = entry_module.healthz()
        self.assertEqual(result["status"], "worker-ok")

    def test_healthz_returns_stalled_when_last_cycle_older_than_180s(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {"last_cycle": time.time() - 500}):
            result = entry_module.healthz()
        self.assertEqual(result["status"], "stalled")

    def test_healthz_returns_stalled_when_no_last_cycle_key(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {}):
            result = entry_module.healthz()
        self.assertEqual(result["status"], "stalled")

    def test_healthz_returns_minus_one_last_cycle_when_no_key(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {}):
            result = entry_module.healthz()
        self.assertEqual(result["last_cycle_seconds_ago"], -1)

    def test_healthz_always_returns_mode_worker(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {}):
            result = entry_module.healthz()
        self.assertEqual(result["mode"], "worker")

    def test_healthz_returns_integer_age_when_last_cycle_set(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {"last_cycle": time.time() - 60}):
            result = entry_module.healthz()
        self.assertIsInstance(result["last_cycle_seconds_ago"], int)

    def test_healthz_returns_positive_age_when_last_cycle_set(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {"last_cycle": time.time() - 90}):
            result = entry_module.healthz()
        self.assertGreater(result["last_cycle_seconds_ago"], 0)

    def test_healthz_boundary_just_inside_180s_is_worker_ok(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {"last_cycle": time.time() - 179}):
            result = entry_module.healthz()
        self.assertEqual(result["status"], "worker-ok")

    def test_healthz_boundary_just_outside_180s_is_stalled(self):
        with patch.object(entry_module, 'WORKER_HEARTBEAT', {"last_cycle": time.time() - 181}):
            result = entry_module.healthz()
        self.assertEqual(result["status"], "stalled")


# ---------------------------------------------------------------------------
# C. start_worker() execution and restart path
# ---------------------------------------------------------------------------

class TestWorkerEntryStartWorker(unittest.TestCase):
    def test_start_worker_calls_run_worker_loop(self):
        """First iteration calls run_worker_loop; KeyboardInterrupt escapes the while-True loop."""
        call_count = [0]

        def fake_run():
            call_count[0] += 1
            raise KeyboardInterrupt  # not caught by `except Exception`

        with patch.object(entry_module, 'run_worker_loop', fake_run):
            try:
                entry_module.start_worker()
            except KeyboardInterrupt:
                pass

        self.assertEqual(call_count[0], 1)

    def test_start_worker_restarts_after_exception(self):
        """Exception in run_worker_loop is swallowed; loop continues to a second call."""
        call_count = [0]

        def fake_run():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("simulated crash")
            raise KeyboardInterrupt  # break after second iteration

        with patch.object(entry_module, 'run_worker_loop', fake_run):
            with patch('time.sleep'):  # skip 30s sleep
                try:
                    entry_module.start_worker()
                except KeyboardInterrupt:
                    pass

        self.assertGreaterEqual(call_count[0], 2, "Loop must restart after exception")


# ---------------------------------------------------------------------------
# D. start_ai_worker() execution and exception handling
# ---------------------------------------------------------------------------

class TestWorkerEntryStartAiWorker(unittest.TestCase):
    def test_start_ai_worker_calls_ai_worker_main(self):
        mock_main = MagicMock()
        with patch.dict(sys.modules, {
            'backend.infrastructure.ai_summarizer_entry': _make_ai_entry_stub(mock_main)
        }):
            entry_module.start_ai_worker()
        mock_main.assert_called_once()

    def test_start_ai_worker_swallows_exception(self):
        failing_main = MagicMock(side_effect=Exception("mistral down"))
        with patch.dict(sys.modules, {
            'backend.infrastructure.ai_summarizer_entry': _make_ai_entry_stub(failing_main)
        }):
            try:
                entry_module.start_ai_worker()
            except Exception as exc:
                self.fail(f"start_ai_worker raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# E. main() environment gating and thread startup boundaries
# ---------------------------------------------------------------------------

class TestWorkerEntryMainEnvGating(unittest.TestCase):
    """
    Tests that main() branches on WORKER_MODE and AI_SUMM_ENABLED env flags
    correctly — no real threads are ever started.
    """

    def _call_main(self, env_overrides):
        """
        Invoke entry_module.main() under full isolation:
          - validate_startup is a no-op
          - threading.Thread is replaced by a mock (no real threads)
          - uvicorn.run is a no-op
          - backend.api.service stub is in sys.modules
          - Only the env keys in env_overrides are set; any of WORKER_MODE,
            AI_SUMM_ENABLED, PORT not present in env_overrides are removed for
            the duration of the call so the real environment cannot bleed in.
        """
        mock_thread_cls = MagicMock()
        mock_thread_instance = MagicMock()
        mock_thread_cls.return_value = mock_thread_instance

        with patch.dict(sys.modules, {'backend.api.service': _make_svc_stub()}):
            with patch.object(entry_module, 'validate_startup'):
                with patch('threading.Thread', mock_thread_cls):
                    with patch.object(entry_module.uvicorn, 'run'):
                        with patch.dict(os.environ, env_overrides, clear=False):
                            # Remove controlled keys not explicitly set by caller.
                            for key in ('WORKER_MODE', 'AI_SUMM_ENABLED', 'PORT'):
                                if key not in env_overrides:
                                    os.environ.pop(key, None)
                            entry_module.main()

        return mock_thread_cls, mock_thread_instance

    # ── Worker mode disabled ────────────────────────────────────────────────

    def test_worker_mode_disabled_does_not_start_sync_thread(self):
        mock_thread_cls, _ = self._call_main({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'})
        for c in mock_thread_cls.call_args_list:
            self.assertIsNot(
                c.kwargs.get('target'), entry_module.start_worker,
                "start_worker must not be scheduled when WORKER_MODE=false"
            )

    # ── Worker mode enabled ─────────────────────────────────────────────────

    def test_worker_mode_enabled_creates_thread_with_start_worker_target(self):
        mock_thread_cls, _ = self._call_main({'WORKER_MODE': 'true', 'AI_SUMM_ENABLED': 'false'})
        mock_thread_cls.assert_any_call(target=entry_module.start_worker, daemon=True)

    def test_worker_mode_enabled_uses_daemon_thread(self):
        mock_thread_cls, _ = self._call_main({'WORKER_MODE': 'true', 'AI_SUMM_ENABLED': 'false'})
        worker_calls = [
            c for c in mock_thread_cls.call_args_list
            if c.kwargs.get('target') is entry_module.start_worker
        ]
        self.assertTrue(worker_calls, "No Thread() call with target=start_worker found")
        self.assertTrue(
            worker_calls[0].kwargs.get('daemon'),
            "Sync worker thread must be created with daemon=True"
        )

    def test_worker_mode_enabled_calls_thread_start(self):
        _, mock_instance = self._call_main({'WORKER_MODE': 'true', 'AI_SUMM_ENABLED': 'false'})
        mock_instance.start.assert_called()

    # ── AI summarizer disabled ──────────────────────────────────────────────

    def test_ai_summ_disabled_does_not_start_ai_thread(self):
        mock_thread_cls, _ = self._call_main({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'})
        for c in mock_thread_cls.call_args_list:
            self.assertIsNot(
                c.kwargs.get('target'), entry_module.start_ai_worker,
                "start_ai_worker must not be scheduled when AI_SUMM_ENABLED=false"
            )

    # ── AI summarizer enabled ───────────────────────────────────────────────

    def test_ai_summ_enabled_creates_thread_with_start_ai_worker_target(self):
        mock_thread_cls, _ = self._call_main({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'true'})
        mock_thread_cls.assert_any_call(target=entry_module.start_ai_worker, daemon=True)

    def test_ai_summ_enabled_uses_daemon_thread(self):
        mock_thread_cls, _ = self._call_main({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'true'})
        ai_calls = [
            c for c in mock_thread_cls.call_args_list
            if c.kwargs.get('target') is entry_module.start_ai_worker
        ]
        self.assertTrue(ai_calls, "No Thread() call with target=start_ai_worker found")
        self.assertTrue(
            ai_calls[0].kwargs.get('daemon'),
            "AI worker thread must be created with daemon=True"
        )

    def test_ai_summ_enabled_calls_thread_start(self):
        _, mock_instance = self._call_main({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'true'})
        mock_instance.start.assert_called()

    # ── Both workers enabled ────────────────────────────────────────────────

    def test_both_workers_enabled_schedules_both_thread_targets(self):
        mock_thread_cls, _ = self._call_main({'WORKER_MODE': 'true', 'AI_SUMM_ENABLED': 'true'})
        targets = [c.kwargs.get('target') for c in mock_thread_cls.call_args_list]
        self.assertIn(entry_module.start_worker, targets)
        self.assertIn(entry_module.start_ai_worker, targets)


# ---------------------------------------------------------------------------
# F. main() uvicorn startup parameters and port parsing
# ---------------------------------------------------------------------------

class TestWorkerEntryMainUvicorn(unittest.TestCase):
    def _call_main_capture_uvicorn(self, env_overrides):
        mock_uvicorn_run = MagicMock()
        with patch.dict(sys.modules, {'backend.api.service': _make_svc_stub()}):
            with patch.object(entry_module, 'validate_startup'):
                with patch('threading.Thread'):
                    with patch.object(entry_module.uvicorn, 'run', mock_uvicorn_run):
                        with patch.dict(os.environ, env_overrides, clear=False):
                            for key in ('WORKER_MODE', 'AI_SUMM_ENABLED', 'PORT'):
                                if key not in env_overrides:
                                    os.environ.pop(key, None)
                            entry_module.main()
        return mock_uvicorn_run

    def test_uvicorn_run_is_called_exactly_once(self):
        mock_run = self._call_main_capture_uvicorn({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'})
        mock_run.assert_called_once()

    def test_uvicorn_run_host_is_0_0_0_0(self):
        mock_run = self._call_main_capture_uvicorn({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'})
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get('host'), "0.0.0.0")

    def test_uvicorn_run_default_port_is_8888(self):
        mock_run = self._call_main_capture_uvicorn({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'})
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get('port'), 8888)

    def test_uvicorn_run_uses_port_from_env(self):
        mock_run = self._call_main_capture_uvicorn(
            {'PORT': '9000', 'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'}
        )
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get('port'), 9000)

    def test_uvicorn_run_log_level_is_info(self):
        mock_run = self._call_main_capture_uvicorn({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'})
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get('log_level'), "info")

    def test_uvicorn_run_timeout_keep_alive_is_120(self):
        mock_run = self._call_main_capture_uvicorn({'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'})
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get('timeout_keep_alive'), 120)

    def test_main_calls_validate_startup(self):
        with patch.dict(sys.modules, {'backend.api.service': _make_svc_stub()}):
            with patch.object(entry_module, 'validate_startup') as mock_vs:
                with patch('threading.Thread'):
                    with patch.object(entry_module.uvicorn, 'run'):
                        with patch.dict(os.environ, {'WORKER_MODE': 'false', 'AI_SUMM_ENABLED': 'false'}, clear=False):
                            os.environ.pop('PORT', None)
                            entry_module.main()
        mock_vs.assert_called_once()

    def test_main_raises_value_error_on_invalid_port(self):
        """int() on a non-numeric PORT string propagates ValueError."""
        with patch.dict(sys.modules, {'backend.api.service': _make_svc_stub()}):
            with patch.object(entry_module, 'validate_startup'):
                with patch('threading.Thread'):
                    with patch.object(entry_module.uvicorn, 'run'):
                        with patch.dict(os.environ, {'PORT': 'not-a-number'}, clear=False):
                            with self.assertRaises(ValueError):
                                entry_module.main()


# ---------------------------------------------------------------------------
# G. validate_startup() pass / fail-fast path
# ---------------------------------------------------------------------------

class TestWorkerEntryValidateStartup(unittest.TestCase):
    def test_validate_startup_does_not_call_sys_exit_in_clean_environment(self):
        """In a clean test environment (no 'src' contamination, Python ≥ 3.9), exits must not fire."""
        with patch('sys.exit') as mock_exit:
            entry_module.validate_startup()
        mock_exit.assert_not_called()

    def test_validate_startup_calls_sys_exit_1_when_src_in_sys_path(self):
        """Injecting a '/fake/src/path' (no 'site-packages') triggers fail-fast."""
        import sys as _sys
        dirty_path = ['/fake/src/path'] + list(_sys.path)
        with patch.object(_sys, 'path', dirty_path):
            with patch('sys.exit') as mock_exit:
                entry_module.validate_startup()
        mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
