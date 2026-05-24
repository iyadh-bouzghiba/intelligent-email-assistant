"""
WORKER-TESTS-01 — Deterministic unit tests for AISummarizerWorker.

Coverage groups:
  W1  AISummaryOutput validation
  W2  _bypass_urgency category mapping
  W3  claim_jobs RPC call behavior
  W4  _fetch_email_row query behavior
  W5  _fetch_thread_context query behavior
  W6  _get_ai_language preference resolution
  W7  _build_prompt XML-delimited content
  W8  _mask_pii PII replacement
  W9  _compute_input_hash determinism
  W10 _check_cache cache-hit / cache-miss / exception
  W11 _write_summary upsert fields and conflict target
  W12 _mark_job_succeeded status update and failure guard
  W13 _mark_job_failed requeue vs dead-letter
  W14 process_batch orchestration and capacity arithmetic
  A   _call_mistral success, governor deferral, retry, and exhaustion
  B   process_job email processing paths
  C   process_document_job error and success paths

No live Supabase, Mistral, Gmail, OAuth, or filesystem access.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.infrastructure.ai_summarizer_worker import (
    AISummaryOutput,
    AISummarizerWorker,
    _bypass_urgency,
    AI_MAX_ATTEMPTS,
    DOCUMENT_JOB_TYPE,
    EMAIL_JOB_TYPE,
    MISTRAL_MAX_OUTPUT_TOKENS,
    MISTRAL_MODEL,
    MISTRAL_TEMPERATURE,
    PROMPT_VERSION,
    RATE_LIMIT_RETRY_DELAYS,
    SUMMARIZATION_SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Shared fake infrastructure
# ---------------------------------------------------------------------------

class FakeResponse:
    """Minimal Supabase response stub."""
    def __init__(self, data):
        self.data = data


def make_chain(data=None, raise_exc=None):
    """
    Fluent MagicMock where every query-builder method (select, eq, …)
    returns self, and execute() returns FakeResponse(data) or raises raise_exc.
    """
    chain = MagicMock()
    if raise_exc is not None:
        chain.execute.side_effect = raise_exc
    else:
        chain.execute.return_value = FakeResponse(data)
    for method in ("select", "eq", "neq", "order", "limit", "update", "upsert"):
        getattr(chain, method).return_value = chain
    return chain


def make_store(rpc_data=None, table_data=None, rpc_exc=None, table_exc=None):
    """Fake SupabaseStore whose .client chains resolve to configured responses."""
    store = MagicMock()
    store.client.rpc.return_value = make_chain(rpc_data, rpc_exc)
    store.client.table.return_value = make_chain(table_data, table_exc)
    return store


def make_worker(store=None, mistral=None):
    """
    Instantiate AISummarizerWorker with faked dependencies.
    EmailPreprocessor and TokenCounter are patched so __init__ does not
    touch the filesystem or any external service.
    """
    if store is None:
        store = make_store()
    if mistral is None:
        mistral = MagicMock()
    with (
        patch("backend.infrastructure.ai_summarizer_worker.EmailPreprocessor"),
        patch("backend.infrastructure.ai_summarizer_worker.TokenCounter"),
    ):
        return AISummarizerWorker(store, mistral)


# ---------------------------------------------------------------------------
# W1 — AISummaryOutput validation
# ---------------------------------------------------------------------------

class TestAISummaryOutput(unittest.TestCase):
    """W1x — Pydantic model accepts valid urgency values and rejects invalid ones."""

    def test_valid_low_urgency(self):
        obj = AISummaryOutput(overview="ok", action_items=[], urgency="low")
        self.assertEqual(obj.urgency, "low")

    def test_valid_medium_urgency(self):
        obj = AISummaryOutput(overview="ok", action_items=["do X"], urgency="medium")
        self.assertEqual(obj.urgency, "medium")

    def test_valid_high_urgency(self):
        obj = AISummaryOutput(overview="ok", action_items=[], urgency="high")
        self.assertEqual(obj.urgency, "high")

    def test_invalid_urgency_raises(self):
        from pydantic import ValidationError
        with self.assertRaises((ValidationError, ValueError)):
            AISummaryOutput(overview="ok", action_items=[], urgency="critical")

    def test_invalid_urgency_empty_string_raises(self):
        from pydantic import ValidationError
        with self.assertRaises((ValidationError, ValueError)):
            AISummaryOutput(overview="ok", action_items=[], urgency="")


# ---------------------------------------------------------------------------
# W2 — _bypass_urgency mapping
# ---------------------------------------------------------------------------

class TestBypassUrgency(unittest.TestCase):
    """W2x — module-level _bypass_urgency maps classifier categories to urgency strings."""

    def test_security_account_maps_to_high(self):
        self.assertEqual(_bypass_urgency("SECURITY_ACCOUNT"), "high")

    def test_financial_legal_maps_to_medium(self):
        self.assertEqual(_bypass_urgency("FINANCIAL_LEGAL"), "medium")

    def test_action_required_maps_to_medium(self):
        self.assertEqual(_bypass_urgency("ACTION_REQUIRED"), "medium")

    def test_unknown_category_maps_to_low(self):
        self.assertEqual(_bypass_urgency("UNCATEGORIZED"), "low")

    def test_empty_string_maps_to_low(self):
        self.assertEqual(_bypass_urgency(""), "low")


# ---------------------------------------------------------------------------
# W3 — claim_jobs RPC behavior
# ---------------------------------------------------------------------------

class TestClaimJobs(unittest.TestCase):
    """W3x — claim_jobs delegates to ai_claim_jobs RPC and handles edge cases."""

    def test_calls_rpc_with_correct_name_and_args(self):
        store = make_store(rpc_data=[{"id": "j1"}])
        worker = make_worker(store=store)
        worker.claim_jobs(batch_size=5, worker_id="worker-1")
        store.client.rpc.assert_called_once_with(
            "ai_claim_jobs",
            {"p_job_type": EMAIL_JOB_TYPE, "p_limit": 5, "p_worker_id": "worker-1"},
        )

    def test_calls_execute_on_rpc_result(self):
        store = make_store(rpc_data=[{"id": "j1"}])
        worker = make_worker(store=store)
        worker.claim_jobs(batch_size=2, worker_id="w")
        store.client.rpc.return_value.execute.assert_called_once()

    def test_returns_response_data_when_present(self):
        jobs = [{"id": "j1"}, {"id": "j2"}]
        store = make_store(rpc_data=jobs)
        worker = make_worker(store=store)
        result = worker.claim_jobs(batch_size=5, worker_id="w")
        self.assertEqual(result, jobs)

    def test_returns_empty_list_when_data_is_empty(self):
        store = make_store(rpc_data=[])
        worker = make_worker(store=store)
        result = worker.claim_jobs(batch_size=5, worker_id="w")
        self.assertEqual(result, [])

    def test_returns_empty_list_when_data_is_none(self):
        store = make_store(rpc_data=None)
        worker = make_worker(store=store)
        result = worker.claim_jobs(batch_size=5, worker_id="w")
        self.assertEqual(result, [])

    def test_returns_empty_list_on_rpc_exception(self):
        store = make_store(rpc_exc=RuntimeError("rpc failed"))
        worker = make_worker(store=store)
        result = worker.claim_jobs(batch_size=5, worker_id="w")
        self.assertEqual(result, [])

    def test_custom_job_type_is_forwarded_in_rpc_params(self):
        store = make_store(rpc_data=[])
        worker = make_worker(store=store)
        worker.claim_jobs(batch_size=1, worker_id="w", job_type=DOCUMENT_JOB_TYPE)
        store.client.rpc.assert_called_once_with(
            "ai_claim_jobs",
            {"p_job_type": DOCUMENT_JOB_TYPE, "p_limit": 1, "p_worker_id": "w"},
        )


# ---------------------------------------------------------------------------
# W4 — _fetch_email_row query behavior
# ---------------------------------------------------------------------------

class TestFetchEmailRow(unittest.TestCase):
    """W4x — _fetch_email_row returns the first row or None."""

    def test_returns_first_row_when_data_present(self):
        row = {"subject": "Hello", "sender": "a@b.com", "date": "2026-01-01", "body": "Hi", "thread_id": "t1"}
        store = make_store(table_data=[row])
        worker = make_worker(store=store)
        result = worker._fetch_email_row("acc1", "msg1")
        self.assertEqual(result, row)

    def test_returns_none_when_data_is_empty(self):
        store = make_store(table_data=[])
        worker = make_worker(store=store)
        result = worker._fetch_email_row("acc1", "msg1")
        self.assertIsNone(result)

    def test_returns_none_on_query_exception(self):
        store = make_store(table_exc=RuntimeError("db error"))
        worker = make_worker(store=store)
        result = worker._fetch_email_row("acc1", "msg1")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# W5 — _fetch_thread_context query behavior
# ---------------------------------------------------------------------------

class TestFetchThreadContext(unittest.TestCase):
    """W5x — _fetch_thread_context returns prior messages or [] on failure."""

    def test_returns_response_data_when_present(self):
        msgs = [{"sender": "x@y.com", "date": "2026-01-01", "body": "ctx"}]
        store = make_store(table_data=msgs)
        worker = make_worker(store=store)
        result = worker._fetch_thread_context("acc1", "thread1", "current_msg")
        self.assertEqual(result, msgs)

    def test_returns_empty_list_when_data_is_none(self):
        store = make_store(table_data=None)
        worker = make_worker(store=store)
        result = worker._fetch_thread_context("acc1", "thread1", "current_msg")
        self.assertEqual(result, [])

    def test_returns_empty_list_on_exception(self):
        store = make_store(table_exc=RuntimeError("db error"))
        worker = make_worker(store=store)
        result = worker._fetch_thread_context("acc1", "thread1", "current_msg")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# W6 — _get_ai_language preference resolution
# ---------------------------------------------------------------------------

class TestGetAiLanguage(unittest.TestCase):
    """W6x — _get_ai_language reads user_preferences and falls back to 'en'."""

    def test_returns_normalized_language_when_present(self):
        store = make_store(table_data=[{"ai_language": "fr"}])
        worker = make_worker(store=store)
        result = worker._get_ai_language("acc1")
        self.assertEqual(result, "fr")

    def test_returns_en_when_no_preference_row(self):
        store = make_store(table_data=[])
        worker = make_worker(store=store)
        result = worker._get_ai_language("acc1")
        self.assertEqual(result, "en")

    def test_returns_en_when_ai_language_is_none(self):
        store = make_store(table_data=[{"ai_language": None}])
        worker = make_worker(store=store)
        result = worker._get_ai_language("acc1")
        self.assertEqual(result, "en")

    def test_returns_en_on_query_exception(self):
        store = make_store(table_exc=RuntimeError("db error"))
        worker = make_worker(store=store)
        result = worker._get_ai_language("acc1")
        self.assertEqual(result, "en")


# ---------------------------------------------------------------------------
# W7 — _build_prompt XML-delimited content
# ---------------------------------------------------------------------------

class TestBuildPrompt(unittest.TestCase):
    """W7x — _build_prompt wraps content in XML delimiters; thread section is conditional."""

    def setUp(self):
        self.worker = make_worker()
        self.email_data = {
            "sender": "alice@example.com",
            "subject": "Meeting tomorrow",
            "date": "2026-05-24",
        }
        self.body = "Let's meet at 10am."
        self.prefix = "Summarize this email:"

    def test_includes_email_metadata_delimiters(self):
        prompt = self.worker._build_prompt(self.email_data, self.body, [], self.prefix)
        self.assertIn("<email_metadata>", prompt)
        self.assertIn("</email_metadata>", prompt)

    def test_includes_current_email_body_delimiters(self):
        prompt = self.worker._build_prompt(self.email_data, self.body, [], self.prefix)
        self.assertIn("<current_email_body>", prompt)
        self.assertIn("</current_email_body>", prompt)

    def test_includes_prior_thread_context_when_context_exists(self):
        ctx = [{"sender": "bob@example.com", "body": "Original message"}]
        prompt = self.worker._build_prompt(self.email_data, self.body, ctx, self.prefix)
        self.assertIn("<prior_thread_context>", prompt)
        self.assertIn("</prior_thread_context>", prompt)

    def test_excludes_prior_thread_context_when_empty(self):
        prompt = self.worker._build_prompt(self.email_data, self.body, [], self.prefix)
        self.assertNotIn("<prior_thread_context>", prompt)

    def test_includes_json_only_instruction(self):
        prompt = self.worker._build_prompt(self.email_data, self.body, [], self.prefix)
        self.assertIn("Respond ONLY with valid JSON", prompt)

    def test_prefix_appears_at_start_of_prompt(self):
        prompt = self.worker._build_prompt(self.email_data, self.body, [], self.prefix)
        self.assertTrue(prompt.startswith(self.prefix))

    def test_email_metadata_values_are_embedded(self):
        prompt = self.worker._build_prompt(self.email_data, self.body, [], self.prefix)
        self.assertIn("alice@example.com", prompt)
        self.assertIn("Meeting tomorrow", prompt)
        self.assertIn("2026-05-24", prompt)


# ---------------------------------------------------------------------------
# W8 — _mask_pii PII replacement
# ---------------------------------------------------------------------------

class TestMaskPii(unittest.TestCase):
    """W8x — _mask_pii replaces email addresses, phone numbers, and URLs."""

    def setUp(self):
        self.worker = make_worker()

    def test_masks_email_address(self):
        result = self.worker._mask_pii("Contact support@example.com for help.")
        self.assertIn("[EMAIL]", result)
        self.assertNotIn("support@example.com", result)

    def test_masks_phone_number_with_dashes(self):
        result = self.worker._mask_pii("Call 555-123-4567 now.")
        self.assertIn("[PHONE]", result)
        self.assertNotIn("555-123-4567", result)

    def test_masks_https_url(self):
        result = self.worker._mask_pii("Visit https://example.com/path?q=1 today.")
        self.assertIn("[URL]", result)
        self.assertNotIn("https://example.com", result)

    def test_empty_string_returns_empty(self):
        self.assertEqual(self.worker._mask_pii(""), "")

    def test_plain_text_without_pii_is_unchanged(self):
        text = "Hello, please review the attached document."
        self.assertEqual(self.worker._mask_pii(text), text)


# ---------------------------------------------------------------------------
# W9 — _compute_input_hash determinism
# ---------------------------------------------------------------------------

class TestComputeInputHash(unittest.TestCase):
    """W9x — _compute_input_hash is deterministic and sensitive to input changes."""

    def setUp(self):
        self.worker = make_worker()

    def test_same_input_produces_same_hash(self):
        h1 = self.worker._compute_input_hash("hello world")
        h2 = self.worker._compute_input_hash("hello world")
        self.assertEqual(h1, h2)

    def test_different_input_produces_different_hash(self):
        h1 = self.worker._compute_input_hash("hello world")
        h2 = self.worker._compute_input_hash("goodbye world")
        self.assertNotEqual(h1, h2)

    def test_hash_is_64_char_hex_string(self):
        h = self.worker._compute_input_hash("test")
        self.assertRegex(h, r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# W10 — _check_cache behavior
# ---------------------------------------------------------------------------

class TestCheckCache(unittest.TestCase):
    """W10x — _check_cache returns True on matching input_hash, False otherwise."""

    INPUT_HASH = "abc123def456abc123def456abc123def456abc123def456abc123def456abc1"

    def test_returns_true_when_hash_matches(self):
        store = make_store(table_data=[{"id": "sum1", "input_hash": self.INPUT_HASH}])
        worker = make_worker(store=store)
        result = worker._check_cache("acc1", "msg1", self.INPUT_HASH)
        self.assertTrue(result)

    def test_returns_false_when_hash_differs(self):
        store = make_store(table_data=[{"id": "sum1", "input_hash": "stale_hash"}])
        worker = make_worker(store=store)
        result = worker._check_cache("acc1", "msg1", self.INPUT_HASH)
        self.assertFalse(result)

    def test_returns_false_when_no_rows(self):
        store = make_store(table_data=[])
        worker = make_worker(store=store)
        result = worker._check_cache("acc1", "msg1", self.INPUT_HASH)
        self.assertFalse(result)

    def test_returns_false_on_exception(self):
        store = make_store(table_exc=RuntimeError("db error"))
        worker = make_worker(store=store)
        result = worker._check_cache("acc1", "msg1", self.INPUT_HASH)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# W11 — _write_summary upsert behavior
# ---------------------------------------------------------------------------

class TestWriteSummary(unittest.TestCase):
    """W11x — _write_summary upserts with all required fields and the correct conflict target."""

    SUMMARY_JSON = {"overview": "Quick summary", "action_items": [], "urgency": "low"}

    def _make(self):
        store = make_store(table_data=None)
        worker = make_worker(store=store)
        return worker, store

    def test_upserts_required_payload_fields(self):
        worker, store = self._make()
        worker._write_summary("acc1", "msg1", "hash123", self.SUMMARY_JSON, "open-mistral-nemo", "en")

        table_chain = store.client.table.return_value
        table_chain.upsert.assert_called_once()
        payload = table_chain.upsert.call_args[0][0]

        self.assertEqual(payload["account_id"], "acc1")
        self.assertEqual(payload["gmail_message_id"], "msg1")
        self.assertEqual(payload["prompt_version"], PROMPT_VERSION)
        self.assertEqual(payload["summary_language"], "en")
        self.assertEqual(payload["model"], "open-mistral-nemo")
        self.assertEqual(payload["input_hash"], "hash123")
        self.assertEqual(payload["summary_json"], self.SUMMARY_JSON)
        self.assertEqual(payload["summary_text"], "Quick summary")

    def test_uses_correct_on_conflict_target(self):
        worker, store = self._make()
        worker._write_summary("acc1", "msg1", "hash123", self.SUMMARY_JSON, "model", "fr")

        table_chain = store.client.table.return_value
        kwargs = table_chain.upsert.call_args[1]
        self.assertEqual(
            kwargs.get("on_conflict"),
            "account_id,gmail_message_id,prompt_version,summary_language",
        )

    def test_targets_email_ai_summaries_table(self):
        worker, store = self._make()
        worker._write_summary("acc1", "msg1", "hash123", self.SUMMARY_JSON, "model", "en")
        store.client.table.assert_called_with("email_ai_summaries")

    def test_summary_text_is_overview_field(self):
        worker, store = self._make()
        summary = {"overview": "Specific text", "action_items": ["act"], "urgency": "high"}
        worker._write_summary("acc1", "msg1", "h", summary, "model", "en")

        payload = store.client.table.return_value.upsert.call_args[0][0]
        self.assertEqual(payload["summary_text"], "Specific text")


# ---------------------------------------------------------------------------
# W12 — _mark_job_succeeded behavior
# ---------------------------------------------------------------------------

class TestMarkJobSucceeded(unittest.TestCase):
    """W12x — _mark_job_succeeded updates status to 'succeeded' and raises on empty response."""

    def test_updates_status_to_succeeded(self):
        store = make_store(table_data=[{"id": "j1", "status": "succeeded"}])
        worker = make_worker(store=store)
        worker._mark_job_succeeded("j1")

        table_chain = store.client.table.return_value
        table_chain.update.assert_called_once()
        payload = table_chain.update.call_args[0][0]
        self.assertEqual(payload["status"], "succeeded")

    def test_raises_runtime_error_when_update_returns_empty_list(self):
        store = make_store(table_data=[])
        worker = make_worker(store=store)
        with self.assertRaises(RuntimeError):
            worker._mark_job_succeeded("j1")

    def test_raises_runtime_error_when_update_returns_none(self):
        store = make_store(table_data=None)
        worker = make_worker(store=store)
        with self.assertRaises(RuntimeError):
            worker._mark_job_succeeded("j1")


# ---------------------------------------------------------------------------
# W13 — _mark_job_failed behavior
# ---------------------------------------------------------------------------

class TestMarkJobFailed(unittest.TestCase):
    """W13x — _mark_job_failed requeues below max attempts and dead-letters at max."""

    def test_requeues_with_queued_status_below_max_attempts(self):
        store = make_store(table_data=None)
        worker = make_worker(store=store)
        worker._mark_job_failed("j1", attempts=0, error_code="SOME_ERROR")

        table_chain = store.client.table.return_value
        payload = table_chain.update.call_args[0][0]
        self.assertEqual(payload["status"], "queued")

    def test_clears_locked_at_and_locked_by_on_requeue(self):
        store = make_store(table_data=None)
        worker = make_worker(store=store)
        worker._mark_job_failed("j1", attempts=0, error_code="SOME_ERROR")

        payload = store.client.table.return_value.update.call_args[0][0]
        self.assertIsNone(payload["locked_at"])
        self.assertIsNone(payload["locked_by"])

    def test_increments_attempts_on_requeue(self):
        store = make_store(table_data=None)
        worker = make_worker(store=store)
        worker._mark_job_failed("j1", attempts=2, error_code="ERR")

        payload = store.client.table.return_value.update.call_args[0][0]
        self.assertEqual(payload["attempts"], 3)

    def test_marks_dead_at_max_attempts(self):
        store = make_store(table_data=None)
        worker = make_worker(store=store)
        worker._mark_job_failed("j1", attempts=AI_MAX_ATTEMPTS - 1, error_code="SOME_ERROR")

        payload = store.client.table.return_value.update.call_args[0][0]
        self.assertEqual(payload["status"], "dead")
        self.assertEqual(payload["attempts"], AI_MAX_ATTEMPTS)

    def test_stores_error_code_on_requeue(self):
        store = make_store(table_data=None)
        worker = make_worker(store=store)
        worker._mark_job_failed("j1", attempts=0, error_code="MISTRAL_FAILED")

        payload = store.client.table.return_value.update.call_args[0][0]
        self.assertEqual(payload["last_error_code"], "MISTRAL_FAILED")


# ---------------------------------------------------------------------------
# W14 — process_batch orchestration
# ---------------------------------------------------------------------------

class TestProcessBatch(unittest.TestCase):
    """W14x — process_batch claims email then document jobs, respects capacity, counts total."""

    @staticmethod
    def _jobs(n, prefix="j"):
        return [{"id": f"{prefix}{i}", "account_id": "acc", "gmail_message_id": f"msg{i}", "attempts": 0} for i in range(n)]

    def test_claims_email_jobs_first(self):
        worker = make_worker()
        claim_order = []

        def fake_claim(batch_size, worker_id, job_type=EMAIL_JOB_TYPE):
            claim_order.append(job_type)
            return self._jobs(1) if job_type == EMAIL_JOB_TYPE else []

        worker.claim_jobs = fake_claim
        worker.process_job = MagicMock()
        worker.process_document_job = MagicMock()
        worker.process_batch(batch_size=5, worker_id="w")

        self.assertEqual(claim_order[0], EMAIL_JOB_TYPE)

    def test_document_jobs_receive_remaining_capacity(self):
        worker = make_worker()
        email_jobs = self._jobs(3)
        claim_sizes = {}

        def fake_claim(batch_size, worker_id, job_type=EMAIL_JOB_TYPE):
            claim_sizes[job_type] = batch_size
            return email_jobs if job_type == EMAIL_JOB_TYPE else []

        worker.claim_jobs = fake_claim
        worker.process_job = MagicMock()
        worker.process_document_job = MagicMock()
        worker.process_batch(batch_size=5, worker_id="w")

        self.assertEqual(claim_sizes[DOCUMENT_JOB_TYPE], 2)

    def test_skips_document_claim_when_no_capacity_remains(self):
        worker = make_worker()
        claim_types = []

        def fake_claim(batch_size, worker_id, job_type=EMAIL_JOB_TYPE):
            claim_types.append(job_type)
            return self._jobs(5)  # always return full batch

        worker.claim_jobs = fake_claim
        worker.process_job = MagicMock()
        worker.process_document_job = MagicMock()
        worker.process_batch(batch_size=5, worker_id="w")

        self.assertNotIn(DOCUMENT_JOB_TYPE, claim_types)

    def test_processes_email_jobs_before_document_jobs(self):
        worker = make_worker()
        email_jobs = self._jobs(2, "e")
        doc_jobs = self._jobs(1, "d")
        process_order = []

        def fake_claim(batch_size, worker_id, job_type=EMAIL_JOB_TYPE):
            return email_jobs if job_type == EMAIL_JOB_TYPE else doc_jobs

        worker.claim_jobs = fake_claim
        worker.process_job = lambda job: process_order.append(("email", job["id"]))
        worker.process_document_job = lambda job: process_order.append(("doc", job["id"]))
        worker.process_batch(batch_size=5, worker_id="w")

        email_indices = [i for i, (t, _) in enumerate(process_order) if t == "email"]
        doc_indices = [i for i, (t, _) in enumerate(process_order) if t == "doc"]
        if email_indices and doc_indices:
            self.assertLess(max(email_indices), min(doc_indices))

    def test_returns_total_processed_count(self):
        worker = make_worker()
        email_jobs = self._jobs(3)
        doc_jobs = self._jobs(2, "d")

        def fake_claim(batch_size, worker_id, job_type=EMAIL_JOB_TYPE):
            return email_jobs if job_type == EMAIL_JOB_TYPE else doc_jobs

        worker.claim_jobs = fake_claim
        worker.process_job = MagicMock()
        worker.process_document_job = MagicMock()

        count = worker.process_batch(batch_size=10, worker_id="w")
        self.assertEqual(count, 5)

    def test_returns_zero_when_no_jobs_claimed(self):
        worker = make_worker()
        worker.claim_jobs = MagicMock(return_value=[])
        worker.process_job = MagicMock()
        worker.process_document_job = MagicMock()

        count = worker.process_batch(batch_size=5, worker_id="w")
        self.assertEqual(count, 0)


# ---------------------------------------------------------------------------
# A — _call_mistral: success, governor deferral, retry, exhaustion
# ---------------------------------------------------------------------------

class TestCallMistral(unittest.TestCase):
    """Ax — _call_mistral Mistral call paths with mocked governor and no real sleeps."""

    _EMAIL_DATA = {"sender": "a@b.com", "subject": "Test email", "date": "2026-05-24"}
    _BODY = "Please review the attached report."
    _ACCOUNT_ID = "acc-test"
    _JOB_ID = "job-test"

    @staticmethod
    def _permissive_gov():
        """Return a get_governor mock whose governor allows background slot immediately."""
        gov = MagicMock()
        gov.wait_for_background_slot.return_value = True
        return MagicMock(return_value=gov)

    def test_a1_success_returns_generated_json(self):
        expected = {"overview": "Summary", "action_items": [], "urgency": "low"}
        mistral = MagicMock()
        mistral.generate_json.return_value = expected
        worker = make_worker(mistral=mistral)

        with patch("backend.infrastructure.mistral_governor.get_governor", self._permissive_gov()):
            result = worker._call_mistral(
                self._EMAIL_DATA, self._BODY, [], "",
                account_id=self._ACCOUNT_ID, job_id=self._JOB_ID,
            )

        self.assertEqual(result, expected)

    def test_a1_success_passes_correct_model_args(self):
        mistral = MagicMock()
        mistral.generate_json.return_value = {"overview": "ok", "action_items": [], "urgency": "low"}
        worker = make_worker(mistral=mistral)

        with patch("backend.infrastructure.mistral_governor.get_governor", self._permissive_gov()):
            worker._call_mistral(
                self._EMAIL_DATA, self._BODY, [], "",
                account_id=self._ACCOUNT_ID, job_id=self._JOB_ID,
            )

        kw = mistral.generate_json.call_args[1]
        self.assertEqual(kw["model"], MISTRAL_MODEL)
        self.assertEqual(kw["max_tokens"], MISTRAL_MAX_OUTPUT_TOKENS)
        self.assertEqual(kw["temperature"], MISTRAL_TEMPERATURE)
        self.assertEqual(kw["system_prompt"], SUMMARIZATION_SYSTEM_PROMPT)
        self.assertEqual(kw["request_context"]["account_id"], self._ACCOUNT_ID)
        self.assertEqual(kw["request_context"]["job_id"], self._JOB_ID)

    def test_a2_governor_deferral_skips_mistral_and_returns_none(self):
        mistral = MagicMock()
        worker = make_worker(mistral=mistral)
        blocking_gov = MagicMock()
        blocking_gov.wait_for_background_slot.return_value = False

        with patch("backend.infrastructure.mistral_governor.get_governor", return_value=blocking_gov):
            result = worker._call_mistral(self._EMAIL_DATA, self._BODY)

        self.assertIsNone(result)
        mistral.generate_json.assert_not_called()

    def test_a3_non_rate_limit_exception_returns_none(self):
        mistral = MagicMock()
        mistral.generate_json.side_effect = RuntimeError("boom")
        worker = make_worker(mistral=mistral)

        with patch("backend.infrastructure.mistral_governor.get_governor", self._permissive_gov()):
            result = worker._call_mistral(self._EMAIL_DATA, self._BODY)

        self.assertIsNone(result)
        self.assertEqual(mistral.generate_json.call_count, 1)

    def test_a4_rate_limit_retries_and_succeeds_on_second_call(self):
        expected = {"overview": "ok", "action_items": [], "urgency": "low"}
        mistral = MagicMock()
        mistral.generate_json.side_effect = [RuntimeError("429 rate limit"), expected]
        worker = make_worker(mistral=mistral)

        with (
            patch("backend.infrastructure.mistral_governor.get_governor", self._permissive_gov()),
            patch("backend.infrastructure.ai_summarizer_worker.time.sleep") as mock_sleep,
        ):
            result = worker._call_mistral(self._EMAIL_DATA, self._BODY)

        self.assertEqual(result, expected)
        self.assertEqual(mistral.generate_json.call_count, 2)
        mock_sleep.assert_called_once_with(RATE_LIMIT_RETRY_DELAYS[0])

    def test_a5_rate_limit_exhaustion_returns_none_after_all_retries(self):
        mistral = MagicMock()
        mistral.generate_json.side_effect = RuntimeError("429 rate limit")
        worker = make_worker(mistral=mistral)
        expected_calls = len(RATE_LIMIT_RETRY_DELAYS) + 1

        with (
            patch("backend.infrastructure.mistral_governor.get_governor", self._permissive_gov()),
            patch("backend.infrastructure.ai_summarizer_worker.time.sleep"),
        ):
            result = worker._call_mistral(self._EMAIL_DATA, self._BODY)

        self.assertIsNone(result)
        self.assertEqual(mistral.generate_json.call_count, expected_calls)


# ---------------------------------------------------------------------------
# B — process_job: email processing paths
# ---------------------------------------------------------------------------

class TestProcessJobEmail(unittest.TestCase):
    """Bx — process_job error and success paths; all external calls are patched."""

    _JOB = {"id": "j1", "account_id": "acc1", "gmail_message_id": "msg1", "attempts": 0}
    _EMAIL_ROW = {
        "subject": "Hello",
        "sender": "a@b.com",
        "date": "2026-01-01",
        "body": "Please review the attached document carefully.",
        "thread_id": "thread1",
    }
    # Realistic prep result: preprocessed body + stats dict
    _PREP = (
        "Please review the attached document carefully.",
        {
            "token_count_estimated": 80,
            "preprocessing_reduction_pct": 10.0,
            "html_stripped": False,
            "signature_removed": False,
            "within_limits": True,
            "truncated": False,
        },
    )

    def _make_worker_ready(self, bypass=False):
        """Worker with preprocessor/token_counter configured for normal flow."""
        worker = make_worker()
        worker.token_counter.should_bypass_summarization.return_value = bypass
        return worker

    def test_b1_missing_email_row_marks_email_not_found(self):
        worker = self._make_worker_ready()
        with (
            patch.object(worker, "_fetch_email_row", return_value=None),
            patch.object(worker, "_mark_job_failed") as mock_fail,
            patch.object(worker, "_call_mistral") as mock_mistral,
        ):
            worker.process_job(self._JOB)

        mock_fail.assert_called_once_with("j1", 0, "EMAIL_NOT_FOUND")
        mock_mistral.assert_not_called()

    def test_b2_short_email_bypass_skips_mistral(self):
        worker = self._make_worker_ready(bypass=True)
        with (
            patch.object(worker, "_fetch_email_row", return_value=self._EMAIL_ROW),
            patch.object(worker, "_get_ai_language", return_value="en"),
            patch.object(worker, "_fetch_thread_context", return_value=[]),
            patch.object(worker, "_preprocess_and_prepare", return_value=self._PREP),
            patch.object(worker, "_write_summary") as mock_write,
            patch.object(worker, "_mark_job_succeeded") as mock_succ,
            patch.object(worker, "_mark_job_failed"),
            patch.object(worker, "_call_mistral") as mock_mistral,
        ):
            worker.process_job(self._JOB)

        mock_mistral.assert_not_called()
        mock_write.assert_called_once()
        mock_succ.assert_called_once_with("j1")

    def test_b2_short_email_bypass_urgency_is_valid(self):
        worker = self._make_worker_ready(bypass=True)
        captured = []

        with (
            patch.object(worker, "_fetch_email_row", return_value=self._EMAIL_ROW),
            patch.object(worker, "_get_ai_language", return_value="en"),
            patch.object(worker, "_fetch_thread_context", return_value=[]),
            patch.object(worker, "_preprocess_and_prepare", return_value=self._PREP),
            patch.object(worker, "_write_summary", side_effect=lambda *a, **k: captured.append(a)),
            patch.object(worker, "_mark_job_succeeded"),
            patch.object(worker, "_mark_job_failed"),
            patch.object(worker, "_call_mistral"),
        ):
            worker.process_job(self._JOB)

        self.assertEqual(len(captured), 1)
        summary_json = captured[0][3]  # 4th positional arg to _write_summary
        self.assertIn(summary_json["urgency"], {"low", "medium", "high"})

    def test_b3_cache_hit_marks_succeeded_without_mistral_or_write(self):
        worker = self._make_worker_ready(bypass=False)
        with (
            patch.object(worker, "_fetch_email_row", return_value=self._EMAIL_ROW),
            patch.object(worker, "_get_ai_language", return_value="en"),
            patch.object(worker, "_fetch_thread_context", return_value=[]),
            patch.object(worker, "_preprocess_and_prepare", return_value=self._PREP),
            patch.object(worker, "_check_cache", return_value=True),
            patch.object(worker, "_call_mistral") as mock_mistral,
            patch.object(worker, "_write_summary") as mock_write,
            patch.object(worker, "_mark_job_succeeded") as mock_succ,
            patch.object(worker, "_mark_job_failed"),
        ):
            worker.process_job(self._JOB)

        mock_mistral.assert_not_called()
        mock_write.assert_not_called()
        mock_succ.assert_called_once_with("j1")

    def test_b4_mistral_failure_marks_mistral_failed(self):
        worker = self._make_worker_ready(bypass=False)
        with (
            patch.object(worker, "_fetch_email_row", return_value=self._EMAIL_ROW),
            patch.object(worker, "_get_ai_language", return_value="en"),
            patch.object(worker, "_fetch_thread_context", return_value=[]),
            patch.object(worker, "_preprocess_and_prepare", return_value=self._PREP),
            patch.object(worker, "_check_cache", return_value=False),
            patch.object(worker, "_call_mistral", return_value=None),
            patch.object(worker, "_write_summary") as mock_write,
            patch.object(worker, "_mark_job_failed") as mock_fail,
            patch.object(worker, "_mark_job_succeeded"),
        ):
            worker.process_job(self._JOB)

        mock_fail.assert_called_once_with("j1", 0, "MISTRAL_FAILED")
        mock_write.assert_not_called()

    def test_b5_validation_failure_marks_validation_failed_without_write(self):
        worker = self._make_worker_ready(bypass=False)
        bad_output = {"overview": "x", "action_items": [], "urgency": "INVALID"}
        with (
            patch.object(worker, "_fetch_email_row", return_value=self._EMAIL_ROW),
            patch.object(worker, "_get_ai_language", return_value="en"),
            patch.object(worker, "_fetch_thread_context", return_value=[]),
            patch.object(worker, "_preprocess_and_prepare", return_value=self._PREP),
            patch.object(worker, "_check_cache", return_value=False),
            patch.object(worker, "_call_mistral", return_value=bad_output),
            patch.object(worker, "_write_summary") as mock_write,
            patch.object(worker, "_mark_job_failed") as mock_fail,
            patch.object(worker, "_mark_job_succeeded"),
        ):
            worker.process_job(self._JOB)

        mock_fail.assert_called_once_with("j1", 0, "VALIDATION_FAILED")
        mock_write.assert_not_called()

    def test_b6_success_writes_summary_and_marks_succeeded(self):
        worker = self._make_worker_ready(bypass=False)
        valid_output = {"overview": "Summary text here", "action_items": ["Do A", "Do B"], "urgency": "medium"}
        captured = []

        with (
            patch.object(worker, "_fetch_email_row", return_value=self._EMAIL_ROW),
            patch.object(worker, "_get_ai_language", return_value="en"),
            patch.object(worker, "_fetch_thread_context", return_value=[]),
            patch.object(worker, "_preprocess_and_prepare", return_value=self._PREP),
            patch.object(worker, "_check_cache", return_value=False),
            patch.object(worker, "_call_mistral", return_value=valid_output),
            patch.object(worker, "_write_summary", side_effect=lambda *a, **k: captured.append(a)),
            patch.object(worker, "_mark_job_succeeded") as mock_succ,
            patch.object(worker, "_mark_job_failed"),
        ):
            worker.process_job(self._JOB)

        self.assertEqual(len(captured), 1)
        mock_succ.assert_called_once_with("j1")
        summary_json = captured[0][3]
        self.assertEqual(summary_json["urgency"], "medium")
        self.assertIn("overview", summary_json)
        self.assertIn("action_items", summary_json)
        self.assertIn("category", summary_json)


# ---------------------------------------------------------------------------
# C — process_document_job: error and success paths
# ---------------------------------------------------------------------------

class TestProcessDocumentJob(unittest.TestCase):
    """Cx — process_document_job: covers all branching paths with faked helpers."""

    @staticmethod
    def _doc_job():
        return {"id": "dj1", "account_id": "acc1", "gmail_message_id": "msg1", "attempts": 0}

    @staticmethod
    def _att_info(filename="report.pdf", mime_type="application/pdf", att_id="att1"):
        return {"filename": filename, "mime_type": mime_type, "attachment_id": att_id, "size": 2048}

    def test_c1_fetch_failure_marks_msg_fetch_failed(self):
        worker = make_worker()
        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value=None),
            patch.object(worker, "_mark_job_failed") as mock_fail,
        ):
            worker.process_document_job(self._doc_job())

        mock_fail.assert_called_once_with("dj1", 0, "MSG_FETCH_FAILED")

    def test_c2_no_attachments_marks_succeeded_without_mistral(self):
        worker = make_worker()
        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value={"payload": {}}),
            patch.object(worker, "_collect_supported_attachments", return_value=[]),
            patch.object(worker, "_mark_job_succeeded") as mock_succ,
            patch.object(worker, "_call_mistral_for_document") as mock_mistral,
        ):
            worker.process_document_job(self._doc_job())

        mock_succ.assert_called_once_with("dj1")
        mock_mistral.assert_not_called()

    def test_c3_auth_required_marks_auth_required(self):
        worker = make_worker()
        att_infos = [self._att_info()]
        fake_provider = MagicMock()
        fake_provider.get_attachment.side_effect = RuntimeError("auth_required")

        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value={"payload": {}}),
            patch.object(worker, "_collect_supported_attachments", return_value=att_infos),
            patch("backend.providers.gmail.GmailProvider", return_value=fake_provider),
            patch.object(worker, "_mark_job_failed") as mock_fail,
        ):
            worker.process_document_job(self._doc_job())

        mock_fail.assert_called_once_with("dj1", 0, "AUTH_REQUIRED")

    def test_c4_all_attachments_skipped_on_download_error_marks_succeeded(self):
        worker = make_worker()
        att_infos = [self._att_info()]
        fake_provider = MagicMock()
        fake_provider.get_attachment.side_effect = RuntimeError("network error")

        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value={"payload": {}}),
            patch.object(worker, "_collect_supported_attachments", return_value=att_infos),
            patch("backend.providers.gmail.GmailProvider", return_value=fake_provider),
            patch.object(worker, "_mark_job_succeeded") as mock_succ,
        ):
            worker.process_document_job(self._doc_job())

        mock_succ.assert_called_once_with("dj1")

    def test_c5_empty_extraction_writes_fallback_and_marks_succeeded(self):
        worker = make_worker()
        att_infos = [self._att_info()]
        fake_provider = MagicMock()
        fake_provider.get_attachment.return_value = (b"bytes", None)
        fake_processor = MagicMock()
        fake_processor.process.return_value = {
            "attachment_filename": "report.pdf",
            "document_type": "pdf",
            "extracted_text": "",
        }

        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value={"payload": {}}),
            patch.object(worker, "_collect_supported_attachments", return_value=att_infos),
            patch("backend.providers.gmail.GmailProvider", return_value=fake_provider),
            patch("backend.infrastructure.ai_summarizer_worker.DocumentProcessor", return_value=fake_processor),
            patch.object(worker, "_write_document_summary") as mock_write,
            patch.object(worker, "_mark_job_succeeded") as mock_succ,
        ):
            worker.process_document_job(self._doc_job())

        mock_write.assert_called_once()
        mock_succ.assert_called_once_with("dj1")

    def test_c6_document_cache_hit_marks_succeeded_without_mistral(self):
        KNOWN_HASH = "c" * 64
        worker = make_worker(store=make_store(table_data=[{"id": "s1", "input_hash": KNOWN_HASH}]))
        att_infos = [self._att_info()]
        fake_provider = MagicMock()
        fake_provider.get_attachment.return_value = (b"bytes", None)
        fake_processor = MagicMock()
        fake_processor.process.return_value = {
            "attachment_filename": "report.pdf",
            "document_type": "pdf",
            "extracted_text": "Some text content",
        }

        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value={"payload": {}}),
            patch.object(worker, "_collect_supported_attachments", return_value=att_infos),
            patch("backend.providers.gmail.GmailProvider", return_value=fake_provider),
            patch("backend.infrastructure.ai_summarizer_worker.DocumentProcessor", return_value=fake_processor),
            patch.object(worker, "_compute_input_hash", return_value=KNOWN_HASH),
            patch.object(worker, "_call_mistral_for_document") as mock_mistral,
            patch.object(worker, "_mark_job_succeeded") as mock_succ,
        ):
            worker.process_document_job(self._doc_job())

        mock_succ.assert_called_once_with("dj1")
        mock_mistral.assert_not_called()

    def test_c7_document_mistral_failure_marks_mistral_failed(self):
        worker = make_worker()
        att_infos = [self._att_info()]
        fake_provider = MagicMock()
        fake_provider.get_attachment.return_value = (b"bytes", None)
        fake_processor = MagicMock()
        fake_processor.process.return_value = {
            "attachment_filename": "report.pdf",
            "document_type": "pdf",
            "extracted_text": "Substantial document content here.",
        }

        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value={"payload": {}}),
            patch.object(worker, "_collect_supported_attachments", return_value=att_infos),
            patch("backend.providers.gmail.GmailProvider", return_value=fake_provider),
            patch("backend.infrastructure.ai_summarizer_worker.DocumentProcessor", return_value=fake_processor),
            patch.object(worker, "_call_mistral_for_document", return_value=None),
            patch.object(worker, "_mark_job_failed") as mock_fail,
            patch.object(worker, "_mark_job_succeeded"),
        ):
            worker.process_document_job(self._doc_job())

        mock_fail.assert_called_once_with("dj1", 0, "MISTRAL_FAILED")

    def test_c8_document_validation_failure_marks_validation_failed(self):
        worker = make_worker()
        att_infos = [self._att_info()]
        fake_provider = MagicMock()
        fake_provider.get_attachment.return_value = (b"bytes", None)
        fake_processor = MagicMock()
        fake_processor.process.return_value = {
            "attachment_filename": "report.pdf",
            "document_type": "pdf",
            "extracted_text": "Substantial document content here.",
        }

        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value={"payload": {}}),
            patch.object(worker, "_collect_supported_attachments", return_value=att_infos),
            patch("backend.providers.gmail.GmailProvider", return_value=fake_provider),
            patch("backend.infrastructure.ai_summarizer_worker.DocumentProcessor", return_value=fake_processor),
            patch.object(worker, "_call_mistral_for_document",
                         return_value={"overview": "x", "action_items": [], "urgency": "INVALID"}),
            patch.object(worker, "_write_document_summary") as mock_write,
            patch.object(worker, "_mark_job_failed") as mock_fail,
            patch.object(worker, "_mark_job_succeeded"),
        ):
            worker.process_document_job(self._doc_job())

        mock_fail.assert_called_once_with("dj1", 0, "VALIDATION_FAILED")
        mock_write.assert_not_called()

    def test_c9_success_writes_summary_with_document_fields(self):
        worker = make_worker()
        att_infos = [self._att_info()]
        fake_provider = MagicMock()
        fake_provider.get_attachment.return_value = (b"bytes", None)
        fake_processor = MagicMock()
        fake_processor.process.return_value = {
            "attachment_filename": "report.pdf",
            "document_type": "pdf",
            "extracted_text": "Substantial document content here.",
        }
        valid_doc_output = {"overview": "Contract summary", "action_items": ["Sign"], "urgency": "high"}
        captured = []

        with (
            patch.object(worker, "_fetch_raw_gmail_message", return_value={"payload": {}}),
            patch.object(worker, "_collect_supported_attachments", return_value=att_infos),
            patch("backend.providers.gmail.GmailProvider", return_value=fake_provider),
            patch("backend.infrastructure.ai_summarizer_worker.DocumentProcessor", return_value=fake_processor),
            patch.object(worker, "_call_mistral_for_document", return_value=valid_doc_output),
            patch.object(worker, "_write_document_summary",
                         side_effect=lambda **kw: captured.append(kw)),
            patch.object(worker, "_mark_job_succeeded") as mock_succ,
            patch.object(worker, "_mark_job_failed"),
        ):
            worker.process_document_job(self._doc_job())

        self.assertEqual(len(captured), 1)
        mock_succ.assert_called_once_with("dj1")
        summary_json = captured[0]["summary_json"]
        self.assertIn("document_filename", summary_json)
        self.assertIn("document_filenames", summary_json)
        self.assertIn("attachment_count", summary_json)
        self.assertEqual(summary_json["urgency"], "high")


if __name__ == "__main__":
    unittest.main()
