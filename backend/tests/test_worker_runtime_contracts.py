"""
WORKER-TESTS-01 — Deterministic unit tests for worker runtime contracts.

Coverage groups:
  A   _fetch_account_records — credential query and cursor resolution
  B   _save_delta_cursor — conditional persistence
  C   _sync_one_account — provider dispatch, error handling, email ingestion
  D   run_worker_loop — controlled-exit paths (schema mismatch, no accounts, disabled)
  E   require_env — environment variable validation
  F   get_stable_worker_id — ID generation
  G   main disabled path
  H   main missing env path
  I   main initialization failure path
  J   main one-iteration loop controlled exit

No live Supabase, Mistral, Gmail, OAuth, network, subprocess, or filesystem access.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import io
import logging
import types

# ── Capture-safety block ────────────────────────────────────────────────────
#
# Root cause: backend/api/service.py executes at module-import time:
#
#   sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)   # line 70
#
# Under pytest, sys.stdout may be a capture proxy whose fileno() returns a fd
# owned by pytest's SpooledTemporaryFile.  os.fdopen() then takes *ownership*
# of that fd.  When the resulting file object is garbage-collected it closes the
# fd, and pytest teardown crashes with "OSError: [Errno 9] Bad file descriptor".
#
# Fix A1 — scoped stub (protects worker.py import):
# Install a minimal stub for backend.api.service ONLY for the duration of
# importing worker_module.  worker.py's top-level
#   from backend.api.service import sio
# picks up the stub (sio=None) instead of the real service, so service.py
# line 70 never runs at this point.  Restore sys.modules immediately after so
# later imports of the real backend.api.service are not blocked by the stub.
_svc_had_prev = 'backend.api.service' in sys.modules
_svc_prev = sys.modules.get('backend.api.service')  # Optional[types.ModuleType]
if not _svc_had_prev:
    _svc_stub = types.ModuleType('backend.api.service')
    _svc_stub.sio = None  # worker checks SOCKETIO_AVAILABLE before using sio
    sys.modules['backend.api.service'] = _svc_stub
    _WORKER_SVC_STUB = _svc_stub  # kept for regression assertion in TestImportIsolation
else:
    _WORKER_SVC_STUB = None  # real module already cached; no stub needed

import backend.infrastructure.worker as worker_module

# Restore sys.modules["backend.api.service"] to its pre-import state.
# Removing the stub ensures test_translate_render_contract.py (and any other
# file) can import the real backend.api.service and get TranslateRenderRequest.
if not _svc_had_prev:
    sys.modules.pop('backend.api.service', None)
elif _svc_prev is not None:
    sys.modules['backend.api.service'] = _svc_prev

# Fix B: worker.py attaches StreamHandler(sys.stdout) at import time.
# Redirect every such handler's stream to a private StringIO so that
# logging.shutdown() (registered via atexit) does not close or flush pytest's
# capture proxy when it iterates all registered handlers at process exit.
# Do NOT call handler.close() here.
for _h in list(worker_module.logger.handlers):
    if hasattr(_h, 'stream'):
        _h.stream = io.StringIO()
worker_module.logger.handlers = [logging.NullHandler()]

# Fix A2 — pre-load the real backend.api.service with os.fdopen neutralized.
# After removing the stub above, if the real service.py is not yet in
# sys.modules we import it now with os.fdopen patched to be a no-op on the
# sys.stdout fd.  This prevents fd theft while fully populating sys.modules so
# that subsequent imports by other test files find the real module already
# cached and do not re-execute service.py line 70.
import os as _os_mod
if 'backend.api.service' not in sys.modules:
    _real_fdopen = _os_mod.fdopen
    def _fdopen_guard(fd, *_a, **_kw):
        try:
            _sfd = sys.stdout.fileno()
        except Exception:
            _sfd = -1  # fileno() unavailable; let real fdopen handle it
        if fd == _sfd:
            return sys.stdout  # neutralize: return existing proxy, no fd theft
        return _real_fdopen(fd, *_a, **_kw)
    _os_mod.fdopen = _fdopen_guard
    try:
        import importlib as _il; _il.import_module('backend.api.service'); del _il
    except Exception:
        pass  # if pre-load fails, subsequent imports will attempt normally
    finally:
        _os_mod.fdopen = _real_fdopen  # always restore, even on exception
    del _fdopen_guard, _real_fdopen
del _os_mod
# ────────────────────────────────────────────────────────────────────────────

import backend.infrastructure.ai_summarizer_entry as entry_module


# ---------------------------------------------------------------------------
# Sentinel exception for escaping patched loops
# ---------------------------------------------------------------------------

class _LoopEscaped(BaseException):
    """Raised by patched time.sleep to escape an otherwise infinite loop.
    Inherits BaseException so it is NOT caught by the worker's bare `except Exception` handler.
    """


# ---------------------------------------------------------------------------
# Fake Supabase chain builder (reused from existing test helpers style)
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, data):
        self.data = data


def _make_chain(data=None, raise_exc=None):
    chain = MagicMock()
    if raise_exc is not None:
        chain.execute.side_effect = raise_exc
    else:
        chain.execute.return_value = _FakeResponse(data)
    for method in ("select", "eq", "neq", "order", "limit", "update", "upsert", "insert"):
        getattr(chain, method).return_value = chain
    return chain


def _make_store(table_data=None, table_exc=None):
    store = MagicMock()
    store.client.table.return_value = _make_chain(table_data, table_exc)
    return store


def _make_control(store=None):
    """Fake ControlPlane with pre-wired store."""
    ctrl = MagicMock()
    ctrl.store = store or _make_store()
    ctrl.max_emails_per_cycle.return_value = 100
    ctrl.is_worker_enabled.return_value = True
    return ctrl


# ---------------------------------------------------------------------------
# Minimal email stub (mirrors provider.get_delta_emails return type)
# ---------------------------------------------------------------------------

class _FakeEmail:
    def __init__(self, message_id="mid-001", subject="Test", sender="a@b.com",
                 body="body", date=None, thread_id="tid-001", has_attachments=False):
        self.message_id = message_id
        self.subject = subject
        self.sender = sender
        self.body = body
        self.date = date
        self.thread_id = thread_id
        self.has_attachments = has_attachments


# ===========================================================================
# A — _fetch_account_records
# ===========================================================================

class TestFetchAccountRecords(unittest.TestCase):

    def _ctrl(self, table_data=None, table_exc=None):
        store = _make_store(table_data=table_data, table_exc=table_exc)
        return _make_control(store)

    # A1 — reads credentials with delta_cursor when available
    def test_returns_delta_cursor_from_row(self):
        data = [{"account_id": "acc1", "provider": "gmail", "delta_cursor": "cursor-abc"}]
        ctrl = self._ctrl(table_data=data)
        records = worker_module._fetch_account_records(ctrl, "primary")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["delta_cursor"], "cursor-abc")

    # A2 — falls back to query without delta_cursor when first query raises
    def test_fallback_query_on_first_exception(self):
        store = MagicMock()
        fallback_chain = _make_chain(
            data=[{"account_id": "acc2", "provider": "gmail"}]
        )
        first_chain = MagicMock()
        first_chain.execute.side_effect = Exception("column missing")
        for method in ("select", "eq", "neq", "order", "limit", "update", "upsert"):
            getattr(first_chain, method).return_value = first_chain

        call_count = {"n": 0}
        def table_side_effect(name):
            call_count["n"] += 1
            return first_chain if call_count["n"] == 1 else fallback_chain

        store.client.table.side_effect = table_side_effect
        store.get_sync_state.return_value = None
        ctrl = _make_control(store)

        records = worker_module._fetch_account_records(ctrl, "primary")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["account_id"], "acc2")

    # A3 — skips rows missing account_id
    def test_skips_rows_missing_account_id(self):
        data = [
            {"account_id": None, "provider": "gmail", "delta_cursor": None},
            {"account_id": "acc3", "provider": "gmail", "delta_cursor": "c"},
        ]
        ctrl = self._ctrl(table_data=data)
        records = worker_module._fetch_account_records(ctrl, "primary")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["account_id"], "acc3")

    # A4 — defaults missing provider to "gmail"
    def test_defaults_missing_provider_to_gmail(self):
        data = [{"account_id": "acc4", "provider": None, "delta_cursor": "c"}]
        ctrl = self._ctrl(table_data=data)
        records = worker_module._fetch_account_records(ctrl, "primary")
        self.assertEqual(records[0]["provider"], "gmail")

    # A5 — when delta_cursor is missing, calls control.store.get_sync_state
    def test_calls_get_sync_state_when_no_delta_cursor(self):
        data = [{"account_id": "acc5", "provider": "gmail", "delta_cursor": None}]
        ctrl = self._ctrl(table_data=data)
        ctrl.store.get_sync_state.return_value = "legacy-cursor"
        records = worker_module._fetch_account_records(ctrl, "primary")
        ctrl.store.get_sync_state.assert_called_once_with("primary", "acc5")
        self.assertEqual(records[0]["delta_cursor"], "legacy-cursor")

    # A6 — if get_sync_state raises, record still included with delta_cursor=None
    def test_get_sync_state_exception_yields_none_cursor(self):
        data = [{"account_id": "acc6", "provider": "gmail", "delta_cursor": None}]
        ctrl = self._ctrl(table_data=data)
        ctrl.store.get_sync_state.side_effect = RuntimeError("db error")
        records = worker_module._fetch_account_records(ctrl, "primary")
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["delta_cursor"])


# ===========================================================================
# B — _save_delta_cursor
# ===========================================================================

class TestSaveDeltaCursor(unittest.TestCase):

    # B1 — returns immediately when delta_cursor is None
    def test_noop_when_cursor_is_none(self):
        ctrl = _make_control()
        worker_module._save_delta_cursor(ctrl, "gmail", "acc1", None)
        ctrl.store.client.table.assert_not_called()

    # B1b — returns immediately when delta_cursor is empty string
    def test_noop_when_cursor_is_empty_string(self):
        ctrl = _make_control()
        worker_module._save_delta_cursor(ctrl, "gmail", "acc1", "")
        ctrl.store.client.table.assert_not_called()

    # B2 — updates credentials table when cursor is present
    def test_updates_credentials_when_cursor_present(self):
        chain = _make_chain(data=[])
        store = MagicMock()
        store.client.table.return_value = chain
        ctrl = _make_control(store)
        worker_module._save_delta_cursor(ctrl, "gmail", "acc2", "new-cursor-xyz")
        store.client.table.assert_called_once_with("credentials")
        chain.update.assert_called_once()
        update_args = chain.update.call_args[0][0]
        self.assertEqual(update_args["delta_cursor"], "new-cursor-xyz")
        self.assertIn("updated_at", update_args)

    # B3 — catches update exceptions without raising
    def test_swallows_update_exception(self):
        chain = _make_chain(raise_exc=Exception("db write failed"))
        store = MagicMock()
        store.client.table.return_value = chain
        ctrl = _make_control(store)
        # Must not raise
        worker_module._save_delta_cursor(ctrl, "gmail", "acc3", "cursor-xyz")


# ===========================================================================
# C — _sync_one_account
# ===========================================================================

class TestSyncOneAccount(unittest.TestCase):

    def setUp(self):
        # Disable socket.io for all tests in this group
        self._socketio_patcher = patch.object(worker_module, "SOCKETIO_AVAILABLE", False)
        self._socketio_patcher.start()

    def tearDown(self):
        self._socketio_patcher.stop()

    def _ctrl_with_emails_table(self, existing_ids=None):
        """Control plane whose emails table returns known existing message IDs."""
        existing_data = [{"gmail_message_id": mid} for mid in (existing_ids or [])]
        chain = _make_chain(data=existing_data)
        store = MagicMock()
        store.client.table.return_value = chain
        store.save_email_atomic.return_value = _FakeResponse({"job_created": True, "job_existed": False})
        store.enqueue_ai_job.return_value = "job-001"
        ctrl = _make_control(store)
        return ctrl

    # C1 — get_provider raises ValueError -> returns without store writes
    def test_returns_on_invalid_provider(self):
        ctrl = _make_control()
        with patch("backend.infrastructure.worker.get_provider", side_effect=ValueError("unknown")):
            worker_module._sync_one_account("acc1", "unknown_prov", None, ctrl, "primary")
        ctrl.store.save_email_atomic.assert_not_called()

    # C2 — provider.get_delta_emails raises RuntimeError with "invalid_grant" -> returns
    def test_returns_on_invalid_grant(self):
        ctrl = _make_control()
        fake_provider = MagicMock()
        fake_provider.get_delta_emails.side_effect = RuntimeError("invalid_grant token expired")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            worker_module._sync_one_account("acc1", "gmail", None, ctrl, "primary")
        ctrl.store.save_email_atomic.assert_not_called()

    # C3 — provider.get_delta_emails raises RuntimeError with "auth_required" -> returns
    def test_returns_on_auth_required(self):
        ctrl = _make_control()
        fake_provider = MagicMock()
        fake_provider.get_delta_emails.side_effect = RuntimeError("auth_required: no token")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            worker_module._sync_one_account("acc1", "gmail", None, ctrl, "primary")
        ctrl.store.save_email_atomic.assert_not_called()

    # C4 — no-op cursor path: last_cursor == current_cursor and no emails -> returns without save
    def test_noop_when_cursor_unchanged_and_no_emails(self):
        ctrl = self._ctrl_with_emails_table()
        fake_provider = MagicMock()
        fake_provider.get_delta_emails.return_value = ([], "stable-cursor")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            worker_module._sync_one_account("acc1", "gmail", "stable-cursor", ctrl, "primary")
        ctrl.store.save_email_atomic.assert_not_called()

    # C5 — missing message_id email is skipped
    def test_skips_email_with_no_message_id(self):
        ctrl = self._ctrl_with_emails_table()
        fake_provider = MagicMock()
        bad_email = _FakeEmail(message_id=None)
        fake_provider.get_delta_emails.return_value = ([bad_email], "new-cursor")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            with patch.object(worker_module, "_save_delta_cursor") as mock_save:
                worker_module._sync_one_account("acc1", "gmail", None, ctrl, "primary")
        ctrl.store.save_email_atomic.assert_not_called()

    # C6 — new email calls save_email_atomic with create_ai_job=True
    def test_new_email_saved_with_ai_job_true(self):
        ctrl = self._ctrl_with_emails_table(existing_ids=[])
        fake_provider = MagicMock()
        email = _FakeEmail(message_id="mid-new")
        fake_provider.get_delta_emails.return_value = ([email], "cursor-v2")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            with patch.object(worker_module, "_save_delta_cursor"):
                worker_module._sync_one_account("acc1", "gmail", None, ctrl, "primary")
        ctrl.store.save_email_atomic.assert_called_once()
        kwargs = ctrl.store.save_email_atomic.call_args[1]
        self.assertTrue(kwargs["create_ai_job"])
        self.assertEqual(kwargs["message_id"], "mid-new")

    # C7 — existing email calls save_email_atomic with create_ai_job=False
    def test_existing_email_saved_with_ai_job_false(self):
        ctrl = self._ctrl_with_emails_table(existing_ids=["mid-existing"])
        fake_provider = MagicMock()
        email = _FakeEmail(message_id="mid-existing")
        fake_provider.get_delta_emails.return_value = ([email], "cursor-v2")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            with patch.object(worker_module, "_save_delta_cursor"):
                worker_module._sync_one_account("acc1", "gmail", None, ctrl, "primary")
        ctrl.store.save_email_atomic.assert_called_once()
        kwargs = ctrl.store.save_email_atomic.call_args[1]
        self.assertFalse(kwargs["create_ai_job"])

    # C8 — document_process_v1 job is enqueued for new emails
    def test_document_job_enqueued_for_new_email(self):
        ctrl = self._ctrl_with_emails_table(existing_ids=[])
        fake_provider = MagicMock()
        email = _FakeEmail(message_id="mid-new2")
        fake_provider.get_delta_emails.return_value = ([email], "cursor-v2")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            with patch.object(worker_module, "_save_delta_cursor"):
                worker_module._sync_one_account("acc1", "gmail", None, ctrl, "primary")
        ctrl.store.enqueue_ai_job.assert_called_once_with(
            account_id="acc1",
            gmail_message_id="mid-new2",
            job_type="document_process_v1",
        )

    # C9 — _save_delta_cursor is called when current_cursor is present
    def test_save_delta_cursor_called_when_cursor_present(self):
        ctrl = self._ctrl_with_emails_table(existing_ids=[])
        fake_provider = MagicMock()
        email = _FakeEmail(message_id="mid-c9")
        fake_provider.get_delta_emails.return_value = ([email], "returned-cursor")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            with patch.object(worker_module, "_save_delta_cursor") as mock_save:
                worker_module._sync_one_account("acc1", "gmail", None, ctrl, "primary")
        mock_save.assert_called_once_with(ctrl, "gmail", "acc1", "returned-cursor")

    # C10 — SOCKETIO_AVAILABLE=False does not break per-account logic
    def test_no_socketio_does_not_raise(self):
        ctrl = self._ctrl_with_emails_table(existing_ids=[])
        fake_provider = MagicMock()
        email = _FakeEmail(message_id="mid-c10")
        fake_provider.get_delta_emails.return_value = ([email], "cursor-c10")
        with patch("backend.infrastructure.worker.get_provider", return_value=fake_provider):
            with patch.object(worker_module, "SOCKETIO_AVAILABLE", False):
                with patch.object(worker_module, "_save_delta_cursor"):
                    # Should complete without error
                    worker_module._sync_one_account("acc1", "gmail", None, ctrl, "primary")
        ctrl.store.save_email_atomic.assert_called_once()


# ===========================================================================
# D — run_worker_loop (controlled-loop tests only)
# ===========================================================================

class TestRunWorkerLoop(unittest.TestCase):

    _ORIGINAL_HEARTBEAT = dict(worker_module.WORKER_HEARTBEAT)

    def setUp(self):
        # Reset shared mutable state before each test
        worker_module.WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        worker_module.ControlPlane.schema_state = "uninitialized"

    def tearDown(self):
        worker_module.WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        worker_module.ControlPlane.schema_state = "uninitialized"

    # D1 — schema mismatch: sys.exit(1) after exhausting retries
    def test_schema_mismatch_calls_sys_exit(self):
        fake_control = MagicMock()
        fake_control.verify_schema.return_value = None  # does not set schema_state

        with patch("backend.infrastructure.worker.ControlPlane", return_value=fake_control) as MockCP:
            MockCP.schema_state = "mismatch"
            with patch("backend.infrastructure.worker.MAX_SCHEMA_RETRIES", 2):
                with patch("backend.infrastructure.worker.time") as mock_time:
                    mock_time.sleep.return_value = None
                    mock_time.time.return_value = 0.0
                    mock_time.strftime.return_value = "2026-01-01"
                    with patch("backend.infrastructure.worker.sys.exit", side_effect=SystemExit(1)) as mock_exit:
                        with self.assertRaises(SystemExit) as cm:
                            worker_module.run_worker_loop()
        mock_exit.assert_called_once_with(1)
        self.assertEqual(cm.exception.code, 1)

    # D2 — no connected accounts path: heartbeat becomes idle_no_accounts
    def test_no_accounts_sets_idle_no_accounts_status(self):
        sleep_calls = {"count": 0}

        def sleep_sentinel(secs):
            sleep_calls["count"] += 1
            if sleep_calls["count"] >= 2:
                raise _LoopEscaped("exit after heartbeat update")

        fake_control = MagicMock()
        fake_control.is_worker_enabled.return_value = True
        fake_control.verify_schema.return_value = None

        with patch("backend.infrastructure.worker.ControlPlane", return_value=fake_control) as MockCP:
            MockCP.schema_state = "ok"
            with patch("backend.infrastructure.worker._fetch_account_records", return_value=[]):
                with patch("backend.infrastructure.worker.time") as mock_time:
                    mock_time.sleep.side_effect = sleep_sentinel
                    mock_time.time.return_value = 0.0
                    mock_time.strftime.return_value = "2026-01-01"
                    with self.assertRaises(_LoopEscaped):
                        worker_module.run_worker_loop()

        self.assertEqual(worker_module.WORKER_HEARTBEAT["status"], "idle_no_accounts")

    # D3 — worker disabled path: heartbeat becomes disabled
    def test_worker_disabled_sets_disabled_status(self):
        sleep_calls = {"count": 0}

        def sleep_sentinel(secs):
            sleep_calls["count"] += 1
            if sleep_calls["count"] >= 2:
                raise _LoopEscaped("exit after disabled update")

        fake_control = MagicMock()
        fake_control.is_worker_enabled.return_value = False
        fake_control.verify_schema.return_value = None

        with patch("backend.infrastructure.worker.ControlPlane", return_value=fake_control) as MockCP:
            MockCP.schema_state = "ok"
            with patch("backend.infrastructure.worker.time") as mock_time:
                mock_time.sleep.side_effect = sleep_sentinel
                mock_time.time.return_value = 0.0
                mock_time.strftime.return_value = "2026-01-01"
                with self.assertRaises(_LoopEscaped):
                    worker_module.run_worker_loop()

        self.assertEqual(worker_module.WORKER_HEARTBEAT["status"], "disabled")


# ===========================================================================
# E — require_env
# ===========================================================================

class TestRequireEnv(unittest.TestCase):

    # E1 — returns True when all named env vars are set
    def test_returns_true_when_all_vars_present(self):
        with patch.dict(os.environ, {"TEST_VAR_A": "value-a", "TEST_VAR_B": "value-b"}):
            result = entry_module.require_env(["TEST_VAR_A", "TEST_VAR_B"])
        self.assertTrue(result)

    # E2 — returns False when any named env var is missing
    def test_returns_false_when_var_missing(self):
        env = {"TEST_VAR_A": "value-a"}
        # Ensure TEST_VAR_MISSING is absent
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("TEST_VAR_MISSING", None)
            result = entry_module.require_env(["TEST_VAR_A", "TEST_VAR_MISSING"])
        self.assertFalse(result)

    # E3 — does not log or print secret values (names only)
    def test_logs_names_not_values(self):
        secret_value = "super-secret-token-12345"
        env = {"TEST_SECRET_X": secret_value}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("TEST_MISSING_Y", None)
            with self.assertLogs("backend.infrastructure.ai_summarizer_entry", level="ERROR") as cm:
                entry_module.require_env(["TEST_SECRET_X", "TEST_MISSING_Y"])
        log_output = "\n".join(cm.output)
        self.assertNotIn(secret_value, log_output)
        self.assertIn("TEST_MISSING_Y", log_output)


# ===========================================================================
# F — get_stable_worker_id
# ===========================================================================

class TestGetStableWorkerId(unittest.TestCase):

    _ORIGINAL_AI_WORKER_ID = entry_module.AI_WORKER_ID

    def tearDown(self):
        entry_module.AI_WORKER_ID = self._ORIGINAL_AI_WORKER_ID

    # F1 — when AI_WORKER_ID is set, returns that value
    def test_returns_module_global_when_set(self):
        entry_module.AI_WORKER_ID = "preset-worker-id"
        result = entry_module.get_stable_worker_id()
        self.assertEqual(result, "preset-worker-id")

    # F2 — otherwise returns hostname-pid format
    def test_returns_hostname_pid_when_not_set(self):
        entry_module.AI_WORKER_ID = None
        with patch("backend.infrastructure.ai_summarizer_entry.socket.gethostname", return_value="testhost"):
            with patch("backend.infrastructure.ai_summarizer_entry.os.getpid", return_value=9999):
                result = entry_module.get_stable_worker_id()
        self.assertEqual(result, "testhost-9999")


# ===========================================================================
# G — main disabled path
# ===========================================================================

class TestMainDisabled(unittest.TestCase):

    _ORIGINAL_HEARTBEAT = dict(entry_module.AI_WORKER_HEARTBEAT)
    _ORIGINAL_ENABLED = entry_module.AI_SUMM_ENABLED

    def setUp(self):
        entry_module.AI_WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        entry_module.AI_SUMM_ENABLED = False

    def tearDown(self):
        entry_module.AI_WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        entry_module.AI_SUMM_ENABLED = self._ORIGINAL_ENABLED

    # G1 — main returns without constructing SupabaseStore, MistralEngine, AISummarizerWorker
    def test_main_disabled_returns_early(self):
        with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore") as MockStore:
            with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine") as MockEngine:
                with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker") as MockWorker:
                    entry_module.main()
        MockStore.assert_not_called()
        MockEngine.assert_not_called()
        MockWorker.assert_not_called()

    # G2 — AI_WORKER_HEARTBEAT updates enabled=False and status=disabled
    def test_main_disabled_updates_heartbeat(self):
        with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore"):
            with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine"):
                with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker"):
                    entry_module.main()
        self.assertFalse(entry_module.AI_WORKER_HEARTBEAT["enabled"])
        self.assertEqual(entry_module.AI_WORKER_HEARTBEAT["status"], "disabled")


# ===========================================================================
# H — main missing env path
# ===========================================================================

class TestMainMissingEnv(unittest.TestCase):

    _ORIGINAL_HEARTBEAT = dict(entry_module.AI_WORKER_HEARTBEAT)
    _ORIGINAL_ENABLED = entry_module.AI_SUMM_ENABLED

    def setUp(self):
        entry_module.AI_WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        entry_module.AI_SUMM_ENABLED = True

    def tearDown(self):
        entry_module.AI_WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        entry_module.AI_SUMM_ENABLED = self._ORIGINAL_ENABLED

    # H1 — main returns when require_env returns False
    def test_main_returns_on_missing_env(self):
        with patch("backend.infrastructure.ai_summarizer_entry.require_env", return_value=False):
            with patch("backend.infrastructure.ai_summarizer_entry.get_stable_worker_id", return_value="wid"):
                with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore") as MockStore:
                    with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine") as MockEngine:
                        with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker") as MockWorker:
                            with patch("backend.infrastructure.ai_summarizer_entry.time") as mock_time:
                                mock_time.time.return_value = 0.0
                                entry_module.main()
        MockStore.assert_not_called()
        MockEngine.assert_not_called()
        MockWorker.assert_not_called()

    # H2 — heartbeat status becomes init_failed and last_error_type is MissingEnvVars
    def test_main_missing_env_sets_heartbeat(self):
        with patch("backend.infrastructure.ai_summarizer_entry.require_env", return_value=False):
            with patch("backend.infrastructure.ai_summarizer_entry.get_stable_worker_id", return_value="wid"):
                with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore"):
                    with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine"):
                        with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker"):
                            with patch("backend.infrastructure.ai_summarizer_entry.time") as mock_time:
                                mock_time.time.return_value = 0.0
                                entry_module.main()
        self.assertEqual(entry_module.AI_WORKER_HEARTBEAT["status"], "init_failed")
        self.assertEqual(entry_module.AI_WORKER_HEARTBEAT["last_error_type"], "MissingEnvVars")


# ===========================================================================
# I — main initialization failure path
# ===========================================================================

class TestMainInitFailure(unittest.TestCase):

    _ORIGINAL_HEARTBEAT = dict(entry_module.AI_WORKER_HEARTBEAT)
    _ORIGINAL_ENABLED = entry_module.AI_SUMM_ENABLED

    def setUp(self):
        entry_module.AI_WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        entry_module.AI_SUMM_ENABLED = True

    def tearDown(self):
        entry_module.AI_WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        entry_module.AI_SUMM_ENABLED = self._ORIGINAL_ENABLED

    # I1/I2/I3 — SupabaseStore raises -> main returns, heartbeat init_failed
    def test_store_init_failure_returns_and_sets_heartbeat(self):
        with patch("backend.infrastructure.ai_summarizer_entry.require_env", return_value=True):
            with patch("backend.infrastructure.ai_summarizer_entry.get_stable_worker_id", return_value="wid"):
                with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore", side_effect=ConnectionError("no db")):
                    with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine") as MockEngine:
                        with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker") as MockWorker:
                            with patch("backend.infrastructure.ai_summarizer_entry.time") as mock_time:
                                mock_time.time.return_value = 0.0
                                entry_module.main()
        MockEngine.assert_not_called()
        MockWorker.assert_not_called()
        self.assertEqual(entry_module.AI_WORKER_HEARTBEAT["status"], "init_failed")
        self.assertEqual(entry_module.AI_WORKER_HEARTBEAT["last_error_type"], "ConnectionError")

    # I — MistralEngine raises -> main returns, heartbeat last_error_type matches
    def test_engine_init_failure_sets_correct_error_type(self):
        with patch("backend.infrastructure.ai_summarizer_entry.require_env", return_value=True):
            with patch("backend.infrastructure.ai_summarizer_entry.get_stable_worker_id", return_value="wid"):
                with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore"):
                    with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine", side_effect=ValueError("bad key")):
                        with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker") as MockWorker:
                            with patch("backend.infrastructure.ai_summarizer_entry.time") as mock_time:
                                mock_time.time.return_value = 0.0
                                entry_module.main()
        MockWorker.assert_not_called()
        self.assertEqual(entry_module.AI_WORKER_HEARTBEAT["last_error_type"], "ValueError")


# ===========================================================================
# J — main one-iteration loop controlled exit
# ===========================================================================

class TestMainLoopControlledExit(unittest.TestCase):

    _ORIGINAL_HEARTBEAT = dict(entry_module.AI_WORKER_HEARTBEAT)
    _ORIGINAL_ENABLED = entry_module.AI_SUMM_ENABLED
    _ORIGINAL_BATCH = entry_module.AI_JOBS_BATCH
    _ORIGINAL_SLEEP = entry_module.AI_IDLE_SLEEP
    _ORIGINAL_WORKER_ID = entry_module.AI_WORKER_ID

    def setUp(self):
        entry_module.AI_WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        entry_module.AI_SUMM_ENABLED = True
        entry_module.AI_JOBS_BATCH = 5
        entry_module.AI_IDLE_SLEEP = 1
        entry_module.AI_WORKER_ID = "test-worker"

    def tearDown(self):
        entry_module.AI_WORKER_HEARTBEAT.update(self._ORIGINAL_HEARTBEAT)
        entry_module.AI_SUMM_ENABLED = self._ORIGINAL_ENABLED
        entry_module.AI_JOBS_BATCH = self._ORIGINAL_BATCH
        entry_module.AI_IDLE_SLEEP = self._ORIGINAL_SLEEP
        entry_module.AI_WORKER_ID = self._ORIGINAL_WORKER_ID

    # J1 — process_batch raises KeyboardInterrupt after one loop
    def test_keyboard_interrupt_exits_loop(self):
        fake_worker = MagicMock()
        fake_worker.process_batch.side_effect = KeyboardInterrupt()

        with patch("backend.infrastructure.ai_summarizer_entry.require_env", return_value=True):
            with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore"):
                with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine"):
                    with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker", return_value=fake_worker):
                        with patch("backend.infrastructure.ai_summarizer_entry.time") as mock_time:
                            mock_time.time.return_value = 0.0
                            entry_module.main()

        fake_worker.process_batch.assert_called_once_with(5, "test-worker")

    # J2 — process_batch called with AI_JOBS_BATCH and worker_id
    def test_process_batch_called_with_correct_args(self):
        entry_module.AI_JOBS_BATCH = 7
        call_args_captured = []

        def side_effect(batch, wid):
            call_args_captured.append((batch, wid))
            raise KeyboardInterrupt()

        fake_worker = MagicMock()
        fake_worker.process_batch.side_effect = side_effect

        with patch("backend.infrastructure.ai_summarizer_entry.require_env", return_value=True):
            with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore"):
                with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine"):
                    with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker", return_value=fake_worker):
                        with patch("backend.infrastructure.ai_summarizer_entry.time") as mock_time:
                            mock_time.time.return_value = 0.0
                            entry_module.main()

        self.assertEqual(call_args_captured[0], (7, "test-worker"))

    # J3 — heartbeat reaches running before shutdown
    def test_heartbeat_reaches_running_before_shutdown(self):
        running_statuses = []

        def side_effect(batch, wid):
            running_statuses.append(entry_module.AI_WORKER_HEARTBEAT.get("status"))
            raise KeyboardInterrupt()

        fake_worker = MagicMock()
        fake_worker.process_batch.side_effect = side_effect

        with patch("backend.infrastructure.ai_summarizer_entry.require_env", return_value=True):
            with patch("backend.infrastructure.ai_summarizer_entry.SupabaseStore"):
                with patch("backend.infrastructure.ai_summarizer_entry.MistralEngine"):
                    with patch("backend.infrastructure.ai_summarizer_entry.AISummarizerWorker", return_value=fake_worker):
                        with patch("backend.infrastructure.ai_summarizer_entry.time") as mock_time:
                            mock_time.time.return_value = 0.0
                            entry_module.main()

        self.assertIn("running", running_statuses)


# ===========================================================================
# K — import isolation regression
# ===========================================================================

class TestImportIsolation(unittest.TestCase):

    # K1 — capture-safety stub must not remain in sys.modules after import
    def test_backend_api_service_stub_not_leaked(self):
        # _WORKER_SVC_STUB is None when the real module was already cached
        # (another test file imported first), so there is nothing to assert.
        if _WORKER_SVC_STUB is not None:
            self.assertIsNot(
                sys.modules.get('backend.api.service'),
                _WORKER_SVC_STUB,
                "capture-safety stub leaked into sys.modules after worker_module import",
            )


if __name__ == "__main__":
    unittest.main()
