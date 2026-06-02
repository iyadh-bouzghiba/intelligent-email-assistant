"""
POLISH01-R1 — Language contract chain tests.

Coverage groups:
  P1  enqueue_ai_job persists ai_language
  P2  worker process_job prefers job.ai_language over account preference
  P3  prompt_builder includes exact-language instruction for all 10 AI languages
  P4  worker language guard refuses obvious English output for non-English target
  P5  normalize_language handles all 10 AI languages

No live Supabase, Mistral, or network access.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.prompt_builder import build_summary_prompt
from backend.languages import normalize_language
from backend.infrastructure.ai_summarizer_worker import _detect_language_mismatch


# ---------------------------------------------------------------------------
# Shared fake infrastructure (mirrors test_ai_summarizer_worker.py)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, data):
        self.data = data


def make_chain(data=None, raise_exc=None):
    chain = MagicMock()
    if raise_exc is not None:
        chain.execute.side_effect = raise_exc
    else:
        chain.execute.return_value = FakeResponse(data)
    for method in ("select", "eq", "neq", "order", "limit", "update", "upsert"):
        getattr(chain, method).return_value = chain
    return chain


def make_store(rpc_data=None, table_data=None):
    store = MagicMock()
    store.client.rpc.return_value = make_chain(rpc_data)
    store.client.table.return_value = make_chain(table_data)
    return store


def make_worker(store=None, mistral=None):
    if store is None:
        store = make_store()
    if mistral is None:
        mistral = MagicMock()
    with (
        patch("backend.infrastructure.ai_summarizer_worker.EmailPreprocessor"),
        patch("backend.infrastructure.ai_summarizer_worker.TokenCounter"),
    ):
        from backend.infrastructure.ai_summarizer_worker import AISummarizerWorker
        return AISummarizerWorker(store, mistral)


# ---------------------------------------------------------------------------
# P1 — enqueue_ai_job persists ai_language
# ---------------------------------------------------------------------------

def _make_enqueue_instance():
    """Return a SupabaseStore instance bypassing __init__, with a fully-wired fake client."""
    from backend.infrastructure.supabase_store import SupabaseStore

    fake_client = MagicMock()
    # The upsert chain: client.table("ai_jobs").upsert(payload, ...).execute()
    upsert_chain = MagicMock()
    upsert_chain.execute.return_value = FakeResponse([{"id": "job-test"}])
    fake_client.table.return_value.upsert.return_value = upsert_chain

    instance = object.__new__(SupabaseStore)
    instance.client = fake_client
    return instance, fake_client


class TestEnqueueAiJobLanguage(unittest.TestCase):
    """P1x — enqueue_ai_job accepts and persists ai_language in the upsert payload."""

    def test_ai_language_included_when_provided(self):
        instance, fake_client = _make_enqueue_instance()
        instance.enqueue_ai_job("acc1", "msg1", ai_language="fr")
        payload = fake_client.table.return_value.upsert.call_args[0][0]
        self.assertEqual(payload.get("ai_language"), "fr")

    def test_ai_language_absent_when_not_provided(self):
        instance, fake_client = _make_enqueue_instance()
        instance.enqueue_ai_job("acc1", "msg1")
        payload = fake_client.table.return_value.upsert.call_args[0][0]
        self.assertNotIn("ai_language", payload)

    def test_all_10_ai_languages_accepted(self):
        for lang in ("en", "fr", "ar", "de", "es", "pt-BR", "tr", "zh", "ja", "ko"):
            instance, fake_client = _make_enqueue_instance()
            instance.enqueue_ai_job("acc1", "msg1", ai_language=lang)
            payload = fake_client.table.return_value.upsert.call_args[0][0]
            self.assertEqual(payload.get("ai_language"), lang, f"language={lang} not in payload")


# ---------------------------------------------------------------------------
# P2 — worker process_job prefers job.ai_language over account preference
# ---------------------------------------------------------------------------

class TestProcessJobLanguageResolution(unittest.TestCase):
    """P2x — process_job uses job.ai_language when present; falls back to _get_ai_language."""

    def _make_job(self, ai_language=None):
        return {
            "id": "job-1",
            "account_id": "acc1",
            "gmail_message_id": "msg1",
            "attempts": 0,
            "ai_language": ai_language,
        }

    def test_job_pinned_language_used_not_account_preference(self):
        worker = make_worker()
        worker._fetch_email_row = MagicMock(return_value={
            "subject": "Test", "sender": "a@b.com", "date": "2026-01-01",
            "body": "Bonjour, voici un résumé.", "thread_id": None,
        })
        worker._fetch_thread_context = MagicMock(return_value=[])
        worker._get_ai_language = MagicMock(return_value="en")
        worker._normalize_ai_language = MagicMock(return_value="fr")
        worker._preprocess_and_prepare = MagicMock(return_value=("prepared", {"token_count_estimated": 100, "truncated": False, "preprocessing_reduction_pct": 0}))
        worker.token_counter.should_bypass_summarization = MagicMock(return_value=True)
        worker._compute_input_hash = MagicMock(return_value="hash1")
        worker._build_hash_payload = MagicMock(return_value="payload")
        worker._write_summary = MagicMock()
        worker._mark_job_succeeded = MagicMock()

        with (
            patch("backend.infrastructure.ai_summarizer_worker.classify_email_category", return_value="UNCATEGORIZED"),
            patch("backend.infrastructure.ai_summarizer_worker.build_summary_prompt", return_value="prompt"),
        ):
            worker.process_job(self._make_job(ai_language="fr"))

        # _get_ai_language must NOT be called — job.ai_language takes priority
        worker._get_ai_language.assert_not_called()
        worker._normalize_ai_language.assert_called_once_with("fr")

    def test_fallback_to_account_preference_when_job_has_no_language(self):
        worker = make_worker()
        worker._fetch_email_row = MagicMock(return_value={
            "subject": "Test", "sender": "a@b.com", "date": "2026-01-01",
            "body": "Hello", "thread_id": None,
        })
        worker._fetch_thread_context = MagicMock(return_value=[])
        worker._get_ai_language = MagicMock(return_value="de")
        worker._preprocess_and_prepare = MagicMock(return_value=("prepared", {"token_count_estimated": 100, "truncated": False, "preprocessing_reduction_pct": 0}))
        worker.token_counter.should_bypass_summarization = MagicMock(return_value=True)
        worker._compute_input_hash = MagicMock(return_value="hash1")
        worker._build_hash_payload = MagicMock(return_value="payload")
        worker._write_summary = MagicMock()
        worker._mark_job_succeeded = MagicMock()

        with (
            patch("backend.infrastructure.ai_summarizer_worker.classify_email_category", return_value="UNCATEGORIZED"),
            patch("backend.infrastructure.ai_summarizer_worker.build_summary_prompt", return_value="prompt"),
        ):
            worker.process_job(self._make_job(ai_language=None))

        # _get_ai_language IS called when job.ai_language is None
        worker._get_ai_language.assert_called_once_with("acc1")


# ---------------------------------------------------------------------------
# P3 — prompt_builder includes exact-language instruction for all 10 AI languages
# ---------------------------------------------------------------------------

class TestPromptBuilderLanguageEnforcement(unittest.TestCase):
    """P3x — build_summary_prompt embeds exact target language name for each AI language."""

    EXPECTED_INSTRUCTION_FRAGMENTS = {
        "en": "strictly in English",
        "fr": "strictly in French",
        "ar": "strictly in Arabic",
        "de": "strictly in German",
        "es": "strictly in Spanish",
        "pt-BR": "strictly in Brazilian Portuguese",
        "tr": "strictly in Turkish",
        "zh": "strictly in Simplified Chinese",
        "ja": "strictly in Japanese",
        "ko": "strictly in Korean",
    }

    def test_english_prompt_contains_language_instruction(self):
        prompt = build_summary_prompt("UNCATEGORIZED", "en")
        self.assertIn("strictly in English", prompt)

    def test_non_english_prompt_contains_do_not_use_english_clause(self):
        for lang in ("fr", "ar", "de", "es", "pt-BR", "tr", "zh", "ja", "ko"):
            prompt = build_summary_prompt("UNCATEGORIZED", lang)
            self.assertIn("Do not use English unless the target language is English", prompt,
                          f"Missing no-English clause for lang={lang}")

    def test_all_10_languages_have_expected_instruction_fragment(self):
        for lang, fragment in self.EXPECTED_INSTRUCTION_FRAGMENTS.items():
            prompt = build_summary_prompt("UNCATEGORIZED", lang)
            self.assertIn(fragment, prompt, f"Missing '{fragment}' for lang={lang}")

    def test_json_only_contract_preserved(self):
        for lang in self.EXPECTED_INSTRUCTION_FRAGMENTS:
            prompt = build_summary_prompt("UNCATEGORIZED", lang)
            self.assertIn("Return ONLY valid JSON", prompt)
            self.assertNotIn("category", prompt.split("Pre-classified category:")[1].split("\n\n")[1],
                             msg=f"'category' leaks into output fields for lang={lang}")

    def test_category_not_in_output_fields_section(self):
        """Verify the JSON schema section never lists 'category' as a required output field."""
        prompt = build_summary_prompt("SECURITY_ACCOUNT", "fr")
        json_section = prompt.split("The JSON must contain exactly")[1]
        self.assertNotIn('"category"', json_section)


# ---------------------------------------------------------------------------
# P4 — worker language guard refuses obvious English output for non-English target
# ---------------------------------------------------------------------------

class TestLanguageMismatchGuard(unittest.TestCase):
    """P4x — _detect_language_mismatch fires on obvious English; passes correct-language text."""

    # Arabic
    def test_arabic_target_with_arabic_text_passes(self):
        self.assertFalse(_detect_language_mismatch("مرحبا بالعالم من النص العربي", "ar"))

    def test_arabic_target_with_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch("Hello world this is a summary of the email", "ar"))

    # Chinese
    def test_chinese_target_with_cjk_text_passes(self):
        self.assertFalse(_detect_language_mismatch("这是一封电子邮件的摘要", "zh"))

    def test_chinese_target_with_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch("Hello world this is a summary of the email", "zh"))

    # Japanese
    def test_japanese_target_with_cjk_text_passes(self):
        self.assertFalse(_detect_language_mismatch("これはメールの要約です", "ja"))

    def test_japanese_target_with_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch("Hello world this is a summary of the email", "ja"))

    # Korean
    def test_korean_target_with_hangul_text_passes(self):
        self.assertFalse(_detect_language_mismatch("안녕하세요 이것은 이메일 요약입니다", "ko"))

    def test_korean_target_with_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch("Hello world this is a summary of the email", "ko"))

    # French (Latin non-English)
    def test_french_target_with_accented_french_text_passes(self):
        self.assertFalse(_detect_language_mismatch("Voici un résumé de l'email reçu.", "fr"))

    def test_french_ascii_only_text_passes(self):
        # Valid ASCII-only French must NOT be rejected — "zero non-ASCII" is not a valid signal
        self.assertFalse(_detect_language_mismatch(
            "Je veux aller au cinema ce soir pour voir un film avec vous", "fr"))

    def test_french_target_with_pure_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch(
            "This email contains important information about the meeting", "fr"))

    # German (Latin non-English)
    def test_german_ascii_only_text_passes(self):
        # Valid ASCII-only German (no umlauts) must NOT be rejected
        self.assertFalse(_detect_language_mismatch(
            "Ich muss das Dokument noch einmal lesen und dann senden", "de"))

    def test_german_target_with_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch(
            "This email contains important information about the meeting", "de"))

    # Spanish (Latin non-English)
    def test_spanish_ascii_only_text_passes(self):
        # Valid ASCII-only Spanish (no tildes) must NOT be rejected
        self.assertFalse(_detect_language_mismatch(
            "El cliente solicito una reunion para revisar el contrato", "es"))

    def test_spanish_target_with_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch(
            "This email contains important information about the meeting", "es"))

    # Portuguese (Latin non-English)
    def test_portuguese_ascii_only_text_passes(self):
        # Valid ASCII-only Portuguese (no cedilla/accents) must NOT be rejected
        self.assertFalse(_detect_language_mismatch(
            "Uma reuniao para revisar como fazer para o cliente", "pt-BR"))

    def test_portuguese_target_with_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch(
            "This email contains important information about the meeting", "pt-BR"))

    # Turkish (Latin non-English)
    def test_turkish_target_with_turkish_text_passes(self):
        self.assertFalse(_detect_language_mismatch(
            "Bu e-posta toplantı hazırlığı ve gerekli takip adımları hakkında bilgi veriyor", "tr"))

    def test_turkish_target_with_english_text_fails(self):
        self.assertTrue(_detect_language_mismatch(
            "This email contains important information about the meeting", "tr"))

    # English target — never mismatches
    def test_english_target_never_mismatches(self):
        self.assertFalse(_detect_language_mismatch("Hello world this is a summary", "en"))

    def test_empty_text_never_mismatches(self):
        self.assertFalse(_detect_language_mismatch("", "ar"))

    def test_unknown_target_language_never_mismatches(self):
        self.assertFalse(_detect_language_mismatch("Hello world", "xx"))

    def test_short_latin_text_does_not_trigger_false_positive(self):
        # Fewer than 6 words — conservative heuristic must not fire
        self.assertFalse(_detect_language_mismatch("Hi Bob", "fr"))


# ---------------------------------------------------------------------------
# P5 — normalize_language handles all 10 AI languages
# ---------------------------------------------------------------------------

class TestNormalizeLanguage(unittest.TestCase):
    """P5x — normalize_language returns canonical codes for all 10 AI languages."""

    def test_all_10_ai_languages_normalize_to_themselves(self):
        for lang in ("en", "fr", "ar", "de", "es", "pt-BR", "tr", "zh", "ja", "ko"):
            self.assertEqual(normalize_language(lang), lang, f"normalize_language({lang!r}) failed")

    def test_unknown_language_defaults_to_en(self):
        self.assertEqual(normalize_language("xx"), "en")

    def test_none_defaults_to_en(self):
        self.assertEqual(normalize_language(None), "en")

    def test_empty_string_defaults_to_en(self):
        self.assertEqual(normalize_language(""), "en")


if __name__ == "__main__":
    unittest.main()
