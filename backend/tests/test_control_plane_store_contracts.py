"""
WORKER-TESTS-01 — Deterministic unit tests for control_plane and supabase_store contracts.

Coverage groups:
  A   ControlPlane singleton and initialization behavior
  B   ControlPlane worker policy / fail-open behavior
  C   ControlPlane schema state / schema version checks
  D   ControlPlane audit logging / control events
  E   SupabaseStore constructor / client handling
  F   SupabaseStore save_email_atomic RPC contract
  G   SupabaseStore enqueue_ai_job upsert contract
  H   SupabaseStore sync state helpers
  I   SupabaseStore credential/account listing safety

No live Supabase, network, subprocess, filesystem, or real secret access.
"""

import os
import sys
import time
import unittest
from unittest.mock import patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.infrastructure.control_plane import ControlPlane
from backend.infrastructure.supabase_store import SupabaseStore


# ---------------------------------------------------------------------------
# Fake Supabase chain infrastructure
# ---------------------------------------------------------------------------

class _FakeResult:
    """Minimal stand-in for a supabase-py APIResponse."""
    def __init__(self, data=None):
        self.data = data


class _FakeChain:
    """
    Chainable fake that records every operation and returns a configurable result.
    Supports: table, rpc, select, eq, single, order, limit, insert, upsert, delete, execute.
    """

    def __init__(self, data=None, raise_on_execute=False):
        self._data = data
        self._raise_on_execute = raise_on_execute
        # Recorded state for assertions
        self.table_name = None
        self.rpc_name = None
        self.rpc_params = None
        self.insert_payload = None
        self.upsert_payload = None
        self.on_conflict_value = None
        self.eq_filters = []
        self.selected_cols = None
        self.execute_called = False

    def select(self, *args, **kwargs):
        self.selected_cols = args[0] if args else None
        return self

    def eq(self, col, val):
        self.eq_filters.append((col, val))
        return self

    def single(self):
        return self

    def order(self, col, **kwargs):
        return self

    def limit(self, n):
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.upsert_payload = payload
        self.on_conflict_value = on_conflict
        return self

    def delete(self):
        return self

    def execute(self):
        self.execute_called = True
        if self._raise_on_execute:
            raise Exception("fake db error")
        return _FakeResult(self._data)


class _FakeClient:
    """Minimal supabase client stub wired to a single _FakeChain."""

    def __init__(self, chain=None):
        self._chain = chain

    def _get_chain(self):
        return self._chain if self._chain is not None else _FakeChain()

    def table(self, name):
        chain = self._get_chain()
        chain.table_name = name
        return chain

    def rpc(self, name, params):
        chain = self._get_chain()
        chain.rpc_name = name
        chain.rpc_params = params
        return chain


class _FakeStore:
    """SupabaseStore stand-in with a fake client."""

    def __init__(self, chain=None):
        self.client = _FakeClient(chain=chain)


# ---------------------------------------------------------------------------
# Helper: reset ControlPlane class-level singleton state between tests
# ---------------------------------------------------------------------------

def _reset_control_plane():
    ControlPlane._instance = None
    ControlPlane._policy_cache = {}
    ControlPlane._last_fetch = 0
    ControlPlane.schema_state = "uninitialized"
    ControlPlane.store = None


# ---------------------------------------------------------------------------
# A. Singleton and initialization behavior
# ---------------------------------------------------------------------------

class TestControlPlaneSingleton(unittest.TestCase):
    def setUp(self):
        _reset_control_plane()

    def tearDown(self):
        _reset_control_plane()

    def _make_cp(self, chain=None):
        fake_store = _FakeStore(chain=chain)
        with patch("backend.infrastructure.control_plane.SupabaseStore", return_value=fake_store):
            return ControlPlane()

    def test_singleton_returns_same_instance_on_repeated_calls(self):
        fake_store = _FakeStore()
        with patch("backend.infrastructure.control_plane.SupabaseStore", return_value=fake_store):
            cp1 = ControlPlane()
            cp2 = ControlPlane()
        self.assertIs(cp1, cp2)

    def test_store_is_initialized_after_construction(self):
        fake_store = _FakeStore()
        with patch("backend.infrastructure.control_plane.SupabaseStore", return_value=fake_store):
            cp = ControlPlane()
        self.assertIsNotNone(cp.store)

    def test_store_init_failure_is_tolerated_and_store_remains_none(self):
        with patch("backend.infrastructure.control_plane.SupabaseStore", side_effect=RuntimeError("no env")):
            cp = ControlPlane()
        self.assertIsNone(cp.store)

    def test_ensure_store_initialized_returns_true_when_store_present(self):
        cp = self._make_cp()
        result = cp._ensure_store_initialized()
        self.assertTrue(result)

    def test_ensure_store_initialized_returns_false_when_store_unavailable(self):
        with patch("backend.infrastructure.control_plane.SupabaseStore", side_effect=RuntimeError("no env")):
            cp = ControlPlane()
        result = cp._ensure_store_initialized()
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# B. Worker policy / fail-open behavior
# ---------------------------------------------------------------------------

class TestControlPlaneWorkerPolicy(unittest.TestCase):
    def setUp(self):
        _reset_control_plane()

    def tearDown(self):
        _reset_control_plane()

    def _make_cp_no_store(self):
        with patch("backend.infrastructure.control_plane.SupabaseStore", side_effect=RuntimeError("no env")):
            return ControlPlane()

    def _make_cp_with_chain(self, chain):
        fake_store = _FakeStore(chain=chain)
        with patch("backend.infrastructure.control_plane.SupabaseStore", return_value=fake_store):
            return ControlPlane()

    def test_fail_open_worker_enabled_when_store_is_none(self):
        cp = self._make_cp_no_store()
        self.assertTrue(cp.is_worker_enabled())

    def test_fail_open_max_emails_per_cycle_when_store_is_none(self):
        cp = self._make_cp_no_store()
        self.assertEqual(cp.max_emails_per_cycle(), 50)

    def test_fail_open_worker_enabled_when_store_query_raises(self):
        chain = _FakeChain(raise_on_execute=True)
        cp = self._make_cp_with_chain(chain)
        self.assertTrue(cp.is_worker_enabled())

    def test_fail_open_max_emails_when_store_query_raises(self):
        chain = _FakeChain(raise_on_execute=True)
        cp = self._make_cp_with_chain(chain)
        self.assertEqual(cp.max_emails_per_cycle(), 50)

    def test_worker_enabled_true_when_policy_sets_true(self):
        chain = _FakeChain(data={"value": {"worker_enabled": True}})
        cp = self._make_cp_with_chain(chain)
        self.assertTrue(cp.is_worker_enabled())

    def test_worker_enabled_false_when_policy_sets_false(self):
        chain = _FakeChain(data={"value": {"worker_enabled": False}})
        cp = self._make_cp_with_chain(chain)
        self.assertFalse(cp.is_worker_enabled())

    def test_max_emails_per_cycle_from_policy_value(self):
        chain = _FakeChain(data={"value": {"max_emails_per_cycle": 100}})
        cp = self._make_cp_with_chain(chain)
        self.assertEqual(cp.max_emails_per_cycle(), 100)

    def test_max_emails_per_cycle_defaults_to_50_when_key_absent(self):
        chain = _FakeChain(data={"value": {}})
        cp = self._make_cp_with_chain(chain)
        self.assertEqual(cp.max_emails_per_cycle(), 50)

    def test_cached_policy_is_reused_within_ttl(self):
        chain = _FakeChain(data={"value": {"worker_enabled": True}})
        cp = self._make_cp_with_chain(chain)
        # Seed cache and mark it as freshly fetched
        cp._policy_cache = {"worker_enabled": False, "max_emails_per_cycle": 7}
        cp._last_fetch = time.time()
        chain.execute_called = False

        result = cp.is_worker_enabled()

        self.assertFalse(result, "Cache value (False) must be returned within TTL")
        self.assertFalse(chain.execute_called, "Store must not be queried while cache is valid")

    def test_cache_refresh_occurs_after_ttl_expiry(self):
        chain = _FakeChain(data={"value": {"worker_enabled": True, "max_emails_per_cycle": 99}})
        cp = self._make_cp_with_chain(chain)
        cp._policy_cache = {"worker_enabled": False}
        cp._last_fetch = time.time() - 200  # force TTL expiry

        result = cp.is_worker_enabled()

        self.assertTrue(result, "Refreshed policy from store must return True")
        self.assertTrue(chain.execute_called, "Store must be queried after TTL expiry")

    def test_get_policy_queries_system_config_table(self):
        chain = _FakeChain(data={"value": {"worker_enabled": True}})
        cp = self._make_cp_with_chain(chain)
        cp.is_worker_enabled()
        self.assertEqual(chain.table_name, "system_config")


# ---------------------------------------------------------------------------
# C. Schema state / schema version checks
# ---------------------------------------------------------------------------

class TestControlPlaneSchemaVerification(unittest.TestCase):
    def setUp(self):
        _reset_control_plane()

    def tearDown(self):
        _reset_control_plane()

    def _make_cp_with_chain(self, chain):
        fake_store = _FakeStore(chain=chain)
        with patch("backend.infrastructure.control_plane.SupabaseStore", return_value=fake_store):
            return ControlPlane()

    def test_get_supported_schema_version_returns_v3(self):
        cp = self._make_cp_with_chain(_FakeChain())
        self.assertEqual(cp.get_supported_schema_version(), "v3")

    def test_verify_schema_success_sets_schema_state_ok(self):
        chain = _FakeChain(data=[{"version": "v3"}])
        cp = self._make_cp_with_chain(chain)
        result = cp.verify_schema()
        self.assertTrue(result)
        self.assertEqual(ControlPlane.schema_state, "ok")

    def test_verify_schema_version_mismatch_sets_state_mismatch(self):
        chain = _FakeChain(data=[{"version": "v1"}])
        cp = self._make_cp_with_chain(chain)
        result = cp.verify_schema()
        self.assertFalse(result)
        self.assertEqual(ControlPlane.schema_state, "mismatch")

    def test_verify_schema_empty_data_sets_state_mismatch(self):
        chain = _FakeChain(data=[])
        cp = self._make_cp_with_chain(chain)
        result = cp.verify_schema()
        self.assertFalse(result)
        self.assertEqual(ControlPlane.schema_state, "mismatch")

    def test_verify_schema_none_data_sets_state_mismatch(self):
        chain = _FakeChain(data=None)
        cp = self._make_cp_with_chain(chain)
        result = cp.verify_schema()
        self.assertFalse(result)
        self.assertEqual(ControlPlane.schema_state, "mismatch")

    def test_verify_schema_exception_sets_state_uninitialized(self):
        chain = _FakeChain(raise_on_execute=True)
        cp = self._make_cp_with_chain(chain)
        result = cp.verify_schema()
        self.assertFalse(result)
        self.assertEqual(ControlPlane.schema_state, "uninitialized")

    def test_verify_schema_does_not_raise_on_store_exception(self):
        chain = _FakeChain(raise_on_execute=True)
        cp = self._make_cp_with_chain(chain)
        try:
            cp.verify_schema()
        except Exception as exc:
            self.fail(f"verify_schema raised unexpectedly: {exc}")

    def test_verify_schema_no_store_sets_state_uninitialized(self):
        with patch("backend.infrastructure.control_plane.SupabaseStore", side_effect=RuntimeError("no env")):
            cp = ControlPlane()
        result = cp.verify_schema()
        self.assertFalse(result)
        self.assertEqual(ControlPlane.schema_state, "uninitialized")

    def test_verify_schema_queries_schema_version_table(self):
        chain = _FakeChain(data=[{"version": "v3"}])
        cp = self._make_cp_with_chain(chain)
        cp.verify_schema()
        self.assertEqual(chain.table_name, "schema_version")


# ---------------------------------------------------------------------------
# D. Audit logging / control events
# ---------------------------------------------------------------------------

class TestControlPlaneAuditLogging(unittest.TestCase):
    def setUp(self):
        _reset_control_plane()

    def tearDown(self):
        _reset_control_plane()

    def _make_cp_with_chain(self, chain):
        fake_store = _FakeStore(chain=chain)
        with patch("backend.infrastructure.control_plane.SupabaseStore", return_value=fake_store):
            return ControlPlane()

    def test_audit_log_inserts_into_audit_log_table(self):
        chain = _FakeChain(data=[])
        cp = self._make_cp_with_chain(chain)
        cp.log_audit(action="sync_start", resource="emails")
        self.assertEqual(chain.table_name, "audit_log")
        self.assertIsNotNone(chain.insert_payload)

    def test_audit_log_payload_contains_expected_fields(self):
        chain = _FakeChain(data=[])
        cp = self._make_cp_with_chain(chain)
        cp.log_audit(action="sync_start", resource="emails", metadata={"count": 5}, tenant_id="primary")
        payload = chain.insert_payload
        self.assertEqual(payload["action"], "sync_start")
        self.assertEqual(payload["resource"], "emails")
        self.assertEqual(payload["tenant_id"], "primary")
        self.assertEqual(payload["metadata"], {"count": 5})
        self.assertIn("timestamp", payload)

    def test_audit_log_metadata_defaults_to_empty_dict(self):
        chain = _FakeChain(data=[])
        cp = self._make_cp_with_chain(chain)
        cp.log_audit(action="x", resource="y")
        self.assertEqual(chain.insert_payload["metadata"], {})

    def test_audit_log_exception_is_swallowed(self):
        chain = _FakeChain(raise_on_execute=True)
        cp = self._make_cp_with_chain(chain)
        try:
            cp.log_audit(action="x", resource="y")
        except Exception as exc:
            self.fail(f"log_audit raised unexpectedly: {exc}")

    def test_audit_log_no_store_does_not_raise(self):
        with patch("backend.infrastructure.control_plane.SupabaseStore", side_effect=RuntimeError("no env")):
            cp = ControlPlane()
        try:
            cp.log_audit(action="x", resource="y")
        except Exception as exc:
            self.fail(f"log_audit raised unexpectedly when store is None: {exc}")

    def test_audit_log_payload_contains_no_secret_fields(self):
        chain = _FakeChain(data=[])
        cp = self._make_cp_with_chain(chain)
        cp.log_audit(action="auth_event", resource="credentials", metadata={"account": "default"})
        payload = chain.insert_payload
        forbidden = {"token", "secret", "password", "access_token", "refresh_token"}
        actual_keys = set(payload.keys())
        self.assertTrue(
            forbidden.isdisjoint(actual_keys),
            f"Audit payload must not contain secret fields; found: {forbidden & actual_keys}"
        )


# ---------------------------------------------------------------------------
# E. SupabaseStore constructor / client handling
# ---------------------------------------------------------------------------

class TestSupabaseStoreConstruction(unittest.TestCase):
    def test_constructor_raises_runtime_error_when_env_vars_missing(self):
        url_backup = os.environ.pop("SUPABASE_URL", None)
        key_backup = os.environ.pop("SUPABASE_SERVICE_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                SupabaseStore()
        finally:
            if url_backup is not None:
                os.environ["SUPABASE_URL"] = url_backup
            if key_backup is not None:
                os.environ["SUPABASE_SERVICE_KEY"] = key_backup

    def test_bypass_init_via_object_new_is_safe(self):
        store = object.__new__(SupabaseStore)
        chain = _FakeChain(data=[{"id": "job-1"}])
        store.client = _FakeClient(chain=chain)
        self.assertIsNotNone(store.client)
        result = store.client.table("test").select("*").execute()
        self.assertEqual(result.data, [{"id": "job-1"}])


# ---------------------------------------------------------------------------
# F. save_email_atomic — RPC contract
# ---------------------------------------------------------------------------

class TestSupabaseStoreSaveEmailAtomic(unittest.TestCase):
    def _make_store(self, chain):
        store = object.__new__(SupabaseStore)
        store.client = _FakeClient(chain=chain)
        return store

    def test_calls_rpc_save_email_with_ai_job_v2(self):
        chain = _FakeChain(data=[{"email_id": "e1", "job_id": "j1", "job_created": True}])
        store = self._make_store(chain)
        store.save_email_atomic(
            subject="Test", sender="a@b.com", date="2024-01-01T00:00:00+00:00",
            message_id="msg-001", account_id="acct-1"
        )
        self.assertEqual(chain.rpc_name, "save_email_with_ai_job_v2")

    def test_rpc_params_include_all_required_fields(self):
        chain = _FakeChain(data=[{"email_id": "e1"}])
        store = self._make_store(chain)
        store.save_email_atomic(
            subject="Hello", sender="x@y.com", date="2024-01-01T00:00:00+00:00",
            body="body text", message_id="msg-111", tenant_id="primary",
            account_id="acct-2", thread_id="thr-1", provider="gmail",
            thread_ref="ref-1", has_attachments=True, create_ai_job=True
        )
        p = chain.rpc_params
        self.assertEqual(p["p_subject"], "Hello")
        self.assertEqual(p["p_sender"], "x@y.com")
        self.assertEqual(p["p_body"], "body text")
        self.assertEqual(p["p_message_id"], "msg-111")
        self.assertEqual(p["p_account_id"], "acct-2")
        self.assertEqual(p["p_tenant_id"], "primary")
        self.assertEqual(p["p_thread_id"], "thr-1")
        self.assertEqual(p["p_provider"], "gmail")
        self.assertEqual(p["p_thread_ref"], "ref-1")
        self.assertTrue(p["p_has_attachments"])

    def test_create_ai_job_true_passed_correctly(self):
        chain = _FakeChain(data=[{"email_id": "e1"}])
        store = self._make_store(chain)
        store.save_email_atomic(
            subject="S", sender="s@s.com", date="2024-01-01T00:00:00Z",
            message_id="m1", create_ai_job=True
        )
        self.assertTrue(chain.rpc_params["p_create_ai_job"])

    def test_create_ai_job_false_passed_correctly(self):
        chain = _FakeChain(data=[{"email_id": "e1"}])
        store = self._make_store(chain)
        store.save_email_atomic(
            subject="S", sender="s@s.com", date="2024-01-01T00:00:00Z",
            message_id="m1", create_ai_job=False
        )
        self.assertFalse(chain.rpc_params["p_create_ai_job"])

    def test_returns_result_when_rpc_data_present(self):
        data = [{"email_id": "e1", "job_id": "j1"}]
        chain = _FakeChain(data=data)
        store = self._make_store(chain)
        result = store.save_email_atomic(
            subject="S", sender="s@s.com", date="2024-01-01T00:00:00Z",
            message_id="m1"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.data, data)

    def test_returns_none_when_rpc_returns_no_data(self):
        chain = _FakeChain(data=None)
        store = self._make_store(chain)
        result = store.save_email_atomic(
            subject="S", sender="s@s.com", date="2024-01-01T00:00:00Z",
            message_id="m1"
        )
        self.assertIsNone(result)

    def test_returns_none_on_rpc_exception(self):
        chain = _FakeChain(raise_on_execute=True)
        store = self._make_store(chain)
        result = store.save_email_atomic(
            subject="S", sender="s@s.com", date="2024-01-01T00:00:00Z",
            message_id="m1"
        )
        self.assertIsNone(result)

    def test_returns_none_when_message_id_is_missing(self):
        chain = _FakeChain(data=[{"email_id": "e1"}])
        store = self._make_store(chain)
        result = store.save_email_atomic(
            subject="S", sender="s@s.com", date="2024-01-01T00:00:00Z",
            message_id=None
        )
        self.assertIsNone(result)
        self.assertFalse(chain.execute_called, "RPC must not be called when message_id is absent")

    def test_naive_timestamp_gets_timezone_suffix_appended(self):
        chain = _FakeChain(data=[{"email_id": "e1"}])
        store = self._make_store(chain)
        store.save_email_atomic(
            subject="S", sender="s@s.com", date="2024-01-01T10:00:00",
            message_id="m2"
        )
        validated = chain.rpc_params["p_date"]
        self.assertTrue(
            "+" in validated or validated.endswith("Z"),
            "Naive timestamp must have a timezone indicator appended"
        )

    def test_body_defaults_to_empty_string_when_none(self):
        chain = _FakeChain(data=[{"email_id": "e1"}])
        store = self._make_store(chain)
        store.save_email_atomic(
            subject="S", sender="s@s.com", date="2024-01-01T00:00:00Z",
            message_id="m1", body=None
        )
        self.assertEqual(chain.rpc_params["p_body"], "")


# ---------------------------------------------------------------------------
# G. enqueue_ai_job — upsert contract
# ---------------------------------------------------------------------------

class TestSupabaseStoreEnqueueAiJob(unittest.TestCase):
    def _make_store(self, chain):
        store = object.__new__(SupabaseStore)
        store.client = _FakeClient(chain=chain)
        return store

    def test_upserts_to_ai_jobs_table(self):
        chain = _FakeChain(data=[{"id": "job-1"}])
        store = self._make_store(chain)
        store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-1")
        self.assertEqual(chain.table_name, "ai_jobs")
        self.assertIsNotNone(chain.upsert_payload)

    def test_on_conflict_target_is_correct(self):
        chain = _FakeChain(data=[{"id": "job-2"}])
        store = self._make_store(chain)
        store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-1")
        self.assertEqual(chain.on_conflict_value, "job_type,account_id,gmail_message_id")

    def test_payload_includes_account_id(self):
        chain = _FakeChain(data=[{"id": "job-3"}])
        store = self._make_store(chain)
        store.enqueue_ai_job(account_id="my-account", gmail_message_id="msg-2")
        self.assertEqual(chain.upsert_payload["account_id"], "my-account")

    def test_payload_includes_gmail_message_id(self):
        chain = _FakeChain(data=[{"id": "job-4"}])
        store = self._make_store(chain)
        store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-xyz")
        self.assertEqual(chain.upsert_payload["gmail_message_id"], "msg-xyz")

    def test_default_job_type_is_email_summarize_v1(self):
        chain = _FakeChain(data=[{"id": "job-5"}])
        store = self._make_store(chain)
        store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-1")
        self.assertEqual(chain.upsert_payload["job_type"], "email_summarize_v1")

    def test_document_process_v1_job_type_is_accepted(self):
        chain = _FakeChain(data=[{"id": "job-6"}])
        store = self._make_store(chain)
        store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-1", job_type="document_process_v1")
        self.assertEqual(chain.upsert_payload["job_type"], "document_process_v1")

    def test_payload_includes_status_queued(self):
        chain = _FakeChain(data=[{"id": "job-7"}])
        store = self._make_store(chain)
        store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-1")
        self.assertEqual(chain.upsert_payload["status"], "queued")

    def test_returns_job_id_when_data_present(self):
        chain = _FakeChain(data=[{"id": "job-42"}])
        store = self._make_store(chain)
        job_id = store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-1")
        self.assertEqual(job_id, "job-42")

    def test_returns_none_when_data_is_empty_list(self):
        chain = _FakeChain(data=[])
        store = self._make_store(chain)
        job_id = store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-1")
        self.assertIsNone(job_id)

    def test_returns_none_on_exception(self):
        chain = _FakeChain(raise_on_execute=True)
        store = self._make_store(chain)
        job_id = store.enqueue_ai_job(account_id="acct-1", gmail_message_id="msg-1")
        self.assertIsNone(job_id)


# ---------------------------------------------------------------------------
# H. Sync state helpers
# ---------------------------------------------------------------------------

class TestSupabaseStoreSyncState(unittest.TestCase):
    def _make_store(self, chain):
        store = object.__new__(SupabaseStore)
        store.client = _FakeClient(chain=chain)
        return store

    def test_get_sync_state_returns_cursor_when_row_exists(self):
        chain = _FakeChain(data=[{"last_history_id": "12345"}])
        store = self._make_store(chain)
        result = store.get_sync_state(tenant_id="primary", account_id="default")
        self.assertEqual(result, "12345")

    def test_get_sync_state_returns_none_when_row_absent(self):
        chain = _FakeChain(data=[])
        store = self._make_store(chain)
        result = store.get_sync_state(tenant_id="primary", account_id="default")
        self.assertIsNone(result)

    def test_get_sync_state_returns_none_on_exception(self):
        chain = _FakeChain(raise_on_execute=True)
        store = self._make_store(chain)
        result = store.get_sync_state(tenant_id="primary", account_id="default")
        self.assertIsNone(result)

    def test_get_sync_state_filters_by_tenant_id_and_account_id(self):
        chain = _FakeChain(data=[{"last_history_id": "999"}])
        store = self._make_store(chain)
        store.get_sync_state(tenant_id="t1", account_id="a1")
        eq_col_names = [col for col, _ in chain.eq_filters]
        self.assertIn("tenant_id", eq_col_names)
        self.assertIn("account_id", eq_col_names)

    def test_set_sync_state_upserts_to_gmail_sync_state_table(self):
        chain = _FakeChain(data=[])
        store = self._make_store(chain)
        store.set_sync_state(tenant_id="primary", account_id="default", last_history_id="99999")
        self.assertEqual(chain.table_name, "gmail_sync_state")
        self.assertIsNotNone(chain.upsert_payload)

    def test_set_sync_state_payload_contains_required_fields(self):
        chain = _FakeChain(data=[])
        store = self._make_store(chain)
        store.set_sync_state(tenant_id="t1", account_id="a1", last_history_id="55555")
        payload = chain.upsert_payload
        self.assertEqual(payload["tenant_id"], "t1")
        self.assertEqual(payload["account_id"], "a1")
        self.assertEqual(payload["last_history_id"], "55555")
        self.assertIn("updated_at", payload)

    def test_set_sync_state_on_conflict_target(self):
        chain = _FakeChain(data=[])
        store = self._make_store(chain)
        store.set_sync_state(tenant_id="primary", account_id="default", last_history_id="1")
        self.assertEqual(chain.on_conflict_value, "tenant_id,account_id")

    def test_set_sync_state_raises_on_exception(self):
        chain = _FakeChain(raise_on_execute=True)
        store = self._make_store(chain)
        with self.assertRaises(Exception):
            store.set_sync_state(tenant_id="primary", account_id="default", last_history_id="1")


# ---------------------------------------------------------------------------
# I. Credential/account listing safety
# ---------------------------------------------------------------------------

class TestSupabaseStoreCredentialListing(unittest.TestCase):
    def _make_store(self, chain):
        store = object.__new__(SupabaseStore)
        store.client = _FakeClient(chain=chain)
        return store

    def test_list_credentials_returns_data_list(self):
        chain = _FakeChain(data=[
            {"account_id": "acct-1", "updated_at": "2024-01-01", "scopes": "email,profile"}
        ])
        store = self._make_store(chain)
        result = store.list_credentials(provider="gmail")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_list_credentials_filters_by_provider(self):
        chain = _FakeChain(data=[])
        store = self._make_store(chain)
        store.list_credentials(provider="gmail")
        eq_values_for_provider = [v for col, v in chain.eq_filters if col == "provider"]
        self.assertIn("gmail", eq_values_for_provider)

    def test_list_credentials_returns_empty_list_on_exception(self):
        chain = _FakeChain(raise_on_execute=True)
        store = self._make_store(chain)
        result = store.list_credentials(provider="gmail")
        self.assertEqual(result, [])

    def test_list_credentials_does_not_select_encrypted_payload(self):
        chain = _FakeChain(data=[])
        store = self._make_store(chain)
        store.list_credentials(provider="gmail")
        selected = chain.selected_cols or ""
        self.assertNotIn("encrypted_payload", selected)

    def test_list_credentials_parses_scopes_string_to_list(self):
        chain = _FakeChain(data=[
            {"account_id": "acct-1", "updated_at": "2024-01-01", "scopes": "email,profile,calendar"}
        ])
        store = self._make_store(chain)
        result = store.list_credentials(provider="gmail")
        self.assertEqual(result[0]["scopes"], ["email", "profile", "calendar"])

    def test_list_credentials_empty_scopes_returns_empty_list(self):
        chain = _FakeChain(data=[
            {"account_id": "acct-2", "updated_at": "2024-01-01", "scopes": ""}
        ])
        store = self._make_store(chain)
        result = store.list_credentials(provider="gmail")
        self.assertEqual(result[0]["scopes"], [])


if __name__ == "__main__":
    unittest.main()
