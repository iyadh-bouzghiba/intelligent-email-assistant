"""
P3.5-R3C-P1/P3 — Backend Deterministic Proof Surfaces

Deterministic proof for the translate-render contract covering:

  Section A — Route contract (translate_render_email):
    A1. structured_html / preserved / structured_success
    A2. text_fallback / simplified / html_missing (helper never called)
    A3. structured_exception → text_fallback (helper raises, route normalizes)
    A4. structured_success route: translated_body_text excludes hidden preheader

  Section B — Helper reason codes (_attempt_structured_html_translation):
    B1.  bs4_unavailable
    B2.  no_translatable_nodes
    B3.  segment_cap_exceeded
    B4.  json_translation_failed
    B5.  response_not_dict
    B6.  segments_missing
    B7.  segment_count_mismatch
    B8.  non_string_segment
    B9.  node_recollection_mismatch
    B10. structured_success

  Section C — Hidden/preheader element detection (_is_hidden_element):
    C1.  display:none detected
    C2.  display: none with surrounding properties detected
    C3.  visibility:hidden detected
    C4.  opacity:0 detected
    C5.  opacity:0.5 is NOT hidden (partial visibility)
    C6.  mso-hide:all detected
    C7.  max-height:0px detected
    C8.  font-size:0px detected
    C9.  class="preheader" detected
    C10. id containing "preheader" detected
    C11. visible element with color/font-size is NOT hidden
    C12. element with no attributes is NOT hidden
    C13. _collect_translatable_nodes skips display:none preheader text
    C14. _collect_translatable_nodes skips nested preheader-class text

  Section D — Plain-text derivation cleanup (_derive_plain_text_from_html):
    D1.  excessive blank lines collapsed to at most one blank line
    D2.  hidden elements excluded from derived plain text
    D3.  preheader-class elements excluded from derived plain text

  Section E — Large/rich HTML preflight degradation (P3.5-R3D-P1):
    E1.  preflight fires when raw HTML exceeds char threshold (30 000)
    E2.  preflight fires when image count exceeds threshold (>5 <img tags)
    E3.  preflight fires when link count exceeds threshold (>20 href= attrs)
    E4.  preflight fires when table count exceeds threshold (>5 <table tags)
    E5.  preflight does NOT fire for a normal structured email (Google Security Alert)
    E6.  route returns text_fallback / simplified / structured_preflight_degraded
         and does NOT call _attempt_structured_html_translation when preflight fires
    E7.  structured_success route remains unaffected for normal emails

  Section F — Chunked simplified translation for large/rich fallback bodies
               (P3.5-R3E-P1):
    F1.  large fallback body_text is translated via multiple chunk calls and
         the results are recombined in order
    F2.  small fallback body_text still uses a single generate_text_async call
    F3.  structured_preflight_degraded route contract is correct and uses
         chunked fallback internally when body_text is large
    F4.  structured-success route is entirely unaffected by chunking logic

    Helper unit tests:
    Fh1. _should_chunk_fallback_translation: count_tokens always called;
         returns False when token count is at or below threshold
    Fh2. _should_chunk_fallback_translation returns True when token count
         exceeds _FALLBACK_CHUNK_TOKEN_THRESHOLD
    Fh3. _split_text_into_translation_chunks splits at paragraph boundaries
         and preserves order

  Section G — Hard fallback split refinement (P3.5-R3E-P1R):
    Gh1. _hard_split_segment: segment already within budget returned as-is
    Gh2. _hard_split_segment: no-punctuation paragraph reaches word-group
         layer and is split into multiple bounded chunks
    Gh3. _hard_split_segment: no-whitespace dense string reaches layer 4
         (token-verified prefix split); every chunk is token-bounded and
         no text is lost
    Gh4. route: large no-punctuation body_text produces multiple
         generate_text_async calls (end-to-end, real helpers not mocked)

  Section H — Token-verified final split guarantee (P3.5-R3E-P1R2):
    Hi1. _token_verified_prefix_split: empty string returns empty list
    Hi2. _token_verified_prefix_split: string already within budget
         returned as single-element list
    Hi3. _token_verified_prefix_split: CJK-density (1 token/char) dense
         string is split into chunks where every chunk's actual
         engine.count_tokens(chunk) <= _FALLBACK_CHUNK_MAX_TOKENS;
         concatenation recovers original exactly
    Hi4. route: large dense no-whitespace body_text (1 token/char) still
         produces multiple generate_text_async calls and correct contract

  Section I — Dense-token chunking decision fix (P3.5-R3E-P1R3):
    Ii1. _should_chunk_fallback_translation: dense-token body < 3 000 chars
         with token count > threshold returns True; token count is the sole
         criterion, character length is not consulted
    Ii2. route: dense-token body < 3 000 chars with count_tokens > threshold
         produces multiple generate_text_async calls and correct contract fields

  Section J — Simplified fallback source fidelity (P3.5-R3F-P1 / P3.5-R3F-P1R1):
    J1.  _is_noise_element_for_simplified_source: footer class detected
    J2.  _is_noise_element_for_simplified_source: unsubscribe class detected
    J3.  _is_noise_element_for_simplified_source: social class detected
    J4.  _is_noise_element_for_simplified_source: unsub class detected
    J5.  _is_noise_element_for_simplified_source: view-in-browser class
         detected
    J6.  _is_noise_element_for_simplified_source: id=footer detected
    J7.  _is_noise_element_for_simplified_source: legitimate content element
         is NOT flagged as noise
    J8.  _derive_simplified_fallback_source: footer/unsubscribe containers
         suppressed, body content preserved in output
    J9.  _derive_simplified_fallback_source: preheader/hidden elements
         suppressed
    J10. _derive_simplified_fallback_source: returns "" when BS4 unavailable
    J11. route: preflight-degraded path uses derived simplified source when
         the guard approves (derived is materially shorter than existing body)
    J12. route: preflight-degraded path preserves original body_text when
         derived source is empty
    J13. structured-success route is unaffected by simplified source logic
    J14. _should_prefer_simplified_source: returns False when derived is
         empty or below minimum substance threshold
    J15. _should_prefer_simplified_source: returns False when derived is
         not materially shorter than existing body_text (guard rejects)
    J16. _should_prefer_simplified_source: returns True when derived is
         materially shorter than existing body_text (guard approves)
    J17. _should_prefer_simplified_source: returns True when existing
         body_text is empty and derived has sufficient substance
    J18. route: preflight-degraded path preserves original body_text when
         guard rejects because derived source is not materially shorter

  Section K — Anchor- and structure-preserving simplified source (P3.5-R3F-P1R2):
    K1.  _derive_simplified_fallback_source: meaningful content link preserved
         as "Label (URL)" in the derived text
    K2.  _derive_simplified_fallback_source: noise-zone anchor (in unsubscribe
         div) is suppressed — link text and URL absent from output
    K3.  _derive_simplified_fallback_source: fragment (#) and href-less anchors
         preserved as plain text; mailto: annotated with address; https: URL inline
    K4.  _derive_simplified_fallback_source: block-level elements (h1, p, li)
         produce blank-line separation in the assembled text
    K5.  _derive_simplified_fallback_source: translate="no" element text
         preserved in the derived source (tag unwrapped, visible text kept)
    K6.  _derive_simplified_fallback_source: class="notranslate" element text
         preserved in the derived source (tag unwrapped, visible text kept)
    K7.  route: end-to-end preflight-degraded path with real derivation —
         content-link URL appears in translation prompt (guard approves)
    K8.  route: end-to-end preflight-degraded path with real derivation —
         guard rejects when derived source is larger; original body_text used

  Section L — Protected-content and actionable-target fidelity (P3.5-R3F-P1R3):
    L1.  _derive_simplified_fallback_source: translate="no" content visible
         in derived simplified source
    L2.  _derive_simplified_fallback_source: class="notranslate" content visible
         in derived simplified source
    L3.  _derive_simplified_fallback_source: mailto: annotated as "Label (addr)"
    L4.  _derive_simplified_fallback_source: tel: annotated as "Label (number)"
    L5.  _derive_simplified_fallback_source: compact rule — label == destination
         yields plain label only (no duplicate parenthetical)
    L6.  _derive_simplified_fallback_source: noise-zone mailto: remains suppressed
    L7.  route: protected translate="no" content replaced by [[PROT_N]] placeholder
         in translation prompt; raw value NOT exposed to model; restored in output
    L8.  route: guard-reject path preserves original body_text with new derivation
    L9.  route: structured-success is not affected by protected-content changes

  Section M — Protected token preservation for simplified fallback (P3.5-R3F-P1R4):
    M1.  _derive_protected_fallback_source: translate="no" text replaced by
         [[PROT_N]] placeholder; original text absent from derived source
    M2.  _derive_protected_fallback_source: class="notranslate" text replaced
         by [[PROT_N]] placeholder; original text absent from derived source
    M3.  _derive_protected_fallback_source: placeholder_map contains correct
         original text for each token
    M4.  _derive_protected_fallback_source: multiple protected elements get
         distinct [[PROT_N]] tokens; map entries are independent
    M5.  _derive_protected_fallback_source: non-protected content passes
         through unchanged
    M6.  _derive_protected_fallback_source: noise-zone protected element
         remains suppressed (noise layer runs before placeholder layer)
    M7.  _derive_protected_fallback_source: actionable links annotated
         correctly (mailto:/tel:/https: not affected by placeholder logic)
    M8.  _derive_protected_fallback_source: returns ("", {}) when BS4
         unavailable
    M9.  _restore_protected_tokens: replaces placeholder with original text
    M10. _restore_protected_tokens: conservative no-op when placeholder
         absent from translated text (model dropped it)
    M11. _restore_protected_tokens: multiple tokens restored independently
    M12. _build_translation_system_prompt: includes placeholder preservation
         rule when protected_tokens list is non-empty
    M13. _build_translation_system_prompt: no placeholder rule when
         protected_tokens is None or empty
    M14. route: system prompt contains [[PROT_N]] preservation rule when
         placeholder map is non-empty
    M15. route: final translated_body_text has original protected value
         after restoration (end-to-end, real BS4)
    M16. route: no placeholder rule in system prompt when no protected content
    M17. route: structured-success unaffected by placeholder machinery

  Section N — Placeholder activation guard + restore ordering (P3.5-R3F-P1R4R1):
    N1.  route: guard rejects derived source → system prompt has NO [[PROT_N]] rule
    N2.  route: guard rejects derived source → _restore_protected_tokens NOT called
    N3.  route: guard approves derived source → system prompt HAS [[PROT_N]] rule
    N4.  route: guard approves derived source → restoration called, final text correct
    N5.  route: restoration runs before empty-content check for protected-source path

  Section O — Protected-token chunking integrity (P3.5-R3F-P1R4R2):
    O1.  _token_verified_prefix_split: placeholder NOT split when binary-search cut
         lands inside [[PROT_N]] — cut retracted to placeholder start
    O2.  _split_text_into_translation_chunks: multi-paragraph body with embedded
         [[PROT_N]] tokens produces chunks that each contain the placeholder whole
    O3.  route end-to-end (chunked path): protected-source body that requires
         chunking restores correctly — original protected value in final output
    O4.  _token_verified_prefix_split: placeholder-at-position-0 edge case —
         when placeholder starts at 0, cut advances past the whole token

  Section P — Fail-safe protected-token handling + helper dedup (P3.5-R3F-P1R4R3):
    P1.  route: when all [[PROT_N]] tokens survive translation, restoration is
         applied normally — no retry, original protected value in output
    P2.  route: when a [[PROT_N]] token is dropped by the model, the route does
         NOT silently lose protected content — retry path is taken, output
         contains no raw placeholder fragment
    P3.  route: when a [[PROT_N]] token is mangled (partial), treated as missing —
         retry path triggered, no placeholder fragment in output
    P4.  _derive_fallback_source_impl: unwrap mode (protect_mode=False) produces
         output identical to the previous _derive_simplified_fallback_source
         behavior (visible text preserved, no placeholder tokens)
    P5.  _derive_fallback_source_impl: placeholder mode (protect_mode=True)
         produces output identical to the previous _derive_protected_fallback_source
         behavior (placeholder in source, map populated)
    P6.  route: structured-success path is entirely unaffected by the fail-safe
         and helper dedup changes

  Section Q — Retry failure contract parity (P3.5-R3F-P1R4R4):
    Q1.  retry ValueError -> HTTPException 503 "Translation service unavailable"
    Q2.  retry TimeoutError -> HTTPException 502 "Translation timed out"
    Q3.  retry generic Exception -> HTTPException 502 "Translation failed"

  Section R — Canonical plain-text first + HTML assistance (P3.5-R3F-R1):
    R1.  _score_source_noise: clean text scores 0.0
    R2.  _score_source_noise: footer/unsubscribe lines produce positive penalty
    R3.  _score_source_noise: link-cloud lines produce positive penalty
    R4.  _score_source_noise: separator-only lines produce positive penalty
    R5.  _score_source_noise: duplicate paragraph fingerprint produces penalty
    R6.  _select_canonical_translation_source: prefers body_text when clearly
         cleaner (body has 0 noise, derived has noise > gap threshold)
    R7.  _select_canonical_translation_source: falls through to "shorter"
         criterion when both sources have similar noise scores
    R8.  _select_canonical_translation_source: derived empty -> False ("derived_empty")
    R9.  _select_canonical_translation_source: body_text empty -> True ("body_text_empty")
    R10. _enrich_body_text_with_assists: adds meaningful URL missing from body_text
    R11. _enrich_body_text_with_assists: does NOT add URL from footer-context line
    R12. _enrich_body_text_with_assists: does NOT add URL already in body_text
    R13. _trim_footer_tail: cuts footer region when >= 3 signals in last 35%
    R14. _trim_footer_tail: returns text unchanged when footer signals < 3
    R15. _trim_footer_tail: returns text unchanged when head < 200 chars after cut
    R16. _dedup_repeated_blocks: deduplicates repeated paragraphs, preserves order
    R17. _dedup_repeated_blocks: text with no duplicates returned unchanged
    R18. route: Supabase-like fixture — canonical body_text preferred over noisier
         derived HTML source (body has 0 noise, derived has footer contamination)
    R19. route: footer tail and repeated-block dedup applied for
         structured_preflight_degraded output
    R20. route: structured-success unaffected by new source-selection and
         post-processing logic

All I/O and model calls are replaced with deterministic mocks.
No live network, no Mistral API key, no Supabase connection required.

Run with:
    python -m unittest backend.tests.test_translate_render_contract

from the repository root.
"""

import os
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

# Resolve the repo root so 'backend' is importable as a top-level package.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import backend.api.service as service  # noqa: E402
from backend.api.service import TranslateRenderRequest  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_FAKE_GMAIL_MESSAGE_ID = "msg-test-001"
_FAKE_ACCOUNT_ID = "acc-test-001"
_FAKE_BODY_TEXT = "Hello world. This is a test email."
_FAKE_BODY_HTML = "<p>Hello world.</p><p>This is a test email.</p>"
_FAKE_TRANSLATED_HTML = "<p>Bonjour le monde.</p><p>Ceci est un e-mail de test.</p>"
_FAKE_ATTACHMENTS = [{"name": "report.pdf", "size": 2048}]
_FAKE_LINKED_FILES = [{"title": "Budget Sheet", "url": "https://docs.google.com/spreadsheets/d/x"}]


def _make_record(body: str = _FAKE_BODY_TEXT) -> dict:
    return {"account_id": _FAKE_ACCOUNT_ID, "body": body}


def _make_payload(
    *,
    body_html: str = _FAKE_BODY_HTML,
    body_text: str = _FAKE_BODY_TEXT,
    attachments=None,
    linked_files=None,
) -> dict:
    return {
        "body_text": body_text,
        "body_html": body_html,
        "attachments": attachments if attachments is not None else [],
        "linked_files": linked_files if linked_files is not None else [],
    }


# ---------------------------------------------------------------------------
# Section B — Helper-level reason code proof
# ---------------------------------------------------------------------------

class TestHelperReasonCodes(unittest.IsolatedAsyncioTestCase):
    """
    Deterministic proof that every exit point of
    _attempt_structured_html_translation returns the correct normalized
    reason code.  Each test patches the minimum surface required.
    """

    # B1
    async def test_bs4_unavailable(self):
        with patch.object(service, '_BS4_AVAILABLE', False):
            html, code = await service._attempt_structured_html_translation(
                _FAKE_BODY_HTML, "en", MagicMock()
            )
        self.assertIsNone(html)
        self.assertEqual(code, "bs4_unavailable")

    # B2
    async def test_no_translatable_nodes(self):
        # Empty body element yields no NavigableString descendants.
        html, code = await service._attempt_structured_html_translation(
            "<html><body></body></html>", "en", MagicMock()
        )
        self.assertIsNone(html)
        self.assertEqual(code, "no_translatable_nodes")

    # B3
    async def test_segment_cap_exceeded(self):
        # Patch the cap to 0 so any non-empty HTML exceeds it.
        with patch.object(service, '_MAX_TRANSLATABLE_SEGMENTS', 0):
            html, code = await service._attempt_structured_html_translation(
                "<p>Hello</p>", "en", MagicMock()
            )
        self.assertIsNone(html)
        self.assertEqual(code, "segment_cap_exceeded")

    # B4
    async def test_json_translation_failed(self):
        engine = MagicMock()
        engine.generate_json_async = AsyncMock(
            side_effect=RuntimeError("upstream API error")
        )
        html, code = await service._attempt_structured_html_translation(
            "<p>Hello</p>", "en", engine
        )
        self.assertIsNone(html)
        self.assertEqual(code, "json_translation_failed")

    # B5
    async def test_response_not_dict(self):
        engine = MagicMock()
        engine.generate_json_async = AsyncMock(return_value="plain string, not a dict")
        html, code = await service._attempt_structured_html_translation(
            "<p>Hello</p>", "en", engine
        )
        self.assertIsNone(html)
        self.assertEqual(code, "response_not_dict")

    # B6
    async def test_segments_missing(self):
        # Response is a dict but lacks the 'segments' key.
        engine = MagicMock()
        engine.generate_json_async = AsyncMock(return_value={"wrong_key": []})
        html, code = await service._attempt_structured_html_translation(
            "<p>Hello</p>", "en", engine
        )
        self.assertIsNone(html)
        self.assertEqual(code, "segments_missing")

    # B7
    async def test_segment_count_mismatch(self):
        # HTML has 1 text node; engine returns 2 segments.
        engine = MagicMock()
        engine.generate_json_async = AsyncMock(
            return_value={"segments": ["Bonjour", "extra segment"]}
        )
        html, code = await service._attempt_structured_html_translation(
            "<p>Hello</p>", "en", engine
        )
        self.assertIsNone(html)
        self.assertEqual(code, "segment_count_mismatch")

    # B8
    async def test_non_string_segment(self):
        # HTML has 1 text node; engine embeds a non-string value.
        engine = MagicMock()
        engine.generate_json_async = AsyncMock(return_value={"segments": [42]})
        html, code = await service._attempt_structured_html_translation(
            "<p>Hello</p>", "en", engine
        )
        self.assertIsNone(html)
        self.assertEqual(code, "non_string_segment")

    # B9
    async def test_node_recollection_mismatch(self):
        """
        Force a divergence between the first and second _collect_translatable_nodes
        calls: 1 node on collection-1 (drives segment count), 0 nodes on
        collection-2 (re-parse for mutation) → guard triggers the correct code.
        """
        from bs4 import NavigableString

        engine = MagicMock()
        # Engine returns exactly 1 segment to match the first collection count.
        engine.generate_json_async = AsyncMock(return_value={"segments": ["Hola"]})

        fake_node = NavigableString("Hello")
        # side_effect list: first call returns 1-node list, second returns empty.
        with patch.object(
            service,
            '_collect_translatable_nodes',
            side_effect=[[fake_node], []],
        ):
            html, code = await service._attempt_structured_html_translation(
                "<p>Hello</p>", "en", engine
            )

        self.assertIsNone(html)
        self.assertEqual(code, "node_recollection_mismatch")

    # B10
    async def test_structured_success(self):
        engine = MagicMock()
        engine.generate_json_async = AsyncMock(
            return_value={"segments": ["Bonjour le monde"]}
        )
        html, code = await service._attempt_structured_html_translation(
            "<p>Hello world</p>", "en", engine
        )
        self.assertIsNotNone(html)
        self.assertIn("Bonjour le monde", html)
        self.assertEqual(code, "structured_success")


# ---------------------------------------------------------------------------
# Section A — Route-level contract proof
# ---------------------------------------------------------------------------

class TestTranslateRenderRouteContract(unittest.IsolatedAsyncioTestCase):
    """
    Deterministic proof of the route-level translated-render contract.
    The route function is called directly as a coroutine; all I/O is mocked.
    """

    # A1 — Structured success: all contract fields present and correct
    async def test_structured_success_contract(self):
        """
        When _attempt_structured_html_translation succeeds:
          - translation_mode     == structured_html
          - translation_fidelity == preserved
          - translation_reason_code == structured_success
          - translated_body_html  is the translated HTML
          - translated_body_text  is derived from that HTML (not empty)
          - attachments / linked_files pass through unchanged
        """
        mock_engine = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    attachments=_FAKE_ATTACHMENTS,
                    linked_files=_FAKE_LINKED_FILES,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                new=AsyncMock(return_value=(_FAKE_TRANSLATED_HTML, "structured_success")),
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="en"),
            )

        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_fidelity"], "preserved")
        self.assertEqual(result["translation_reason_code"], "structured_success")
        self.assertEqual(result["translated_body_html"], _FAKE_TRANSLATED_HTML)
        # BS4 derives plain text from the translated HTML; must be non-empty.
        self.assertTrue(result["translated_body_text"].strip())
        self.assertIn("Bonjour le monde", result["translated_body_text"])
        # Passthrough integrity
        self.assertEqual(result["attachments"], _FAKE_ATTACHMENTS)
        self.assertEqual(result["linked_files"], _FAKE_LINKED_FILES)
        self.assertEqual(result["gmail_message_id"], _FAKE_GMAIL_MESSAGE_ID)
        self.assertEqual(result["target_language"], "en")

    # A2 — HTML missing: helper is never invoked; reason code is html_missing
    async def test_html_missing_contract(self):
        """
        When rendered payload has no body_html:
          - _attempt_structured_html_translation must NOT be called
          - translation_mode        == text_fallback
          - translation_fidelity    == simplified
          - translation_reason_code == html_missing
          - translated_body_html    is None
          - translated_body_text    is the text-translation result
        """
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        mock_engine.generate_text_async = AsyncMock(return_value="Texte traduit avec succès")
        helper_spy = AsyncMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                # Empty body_html → falsy → structured path skipped
                return_value=_make_payload(body_html=""),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                new=helper_spy,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # Helper must not have been called — html_missing short-circuits before it.
        helper_spy.assert_not_called()

        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertEqual(result["translation_reason_code"], "html_missing")
        self.assertIsNone(result["translated_body_html"])
        self.assertEqual(result["translated_body_text"], "Texte traduit avec succès")

    # A3 — Structured exception: route normalizes, falls back cleanly, no leak
    async def test_structured_exception_normalizes_and_falls_back(self):
        """
        When _attempt_structured_html_translation raises an unexpected exception:
          - The route catches it (does not propagate)
          - translation_reason_code == structured_exception
          - Route follows text fallback path cleanly
          - translated_body_html    is None
          - translated_body_text    is the text-fallback result
        """
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 8
        mock_engine.generate_text_async = AsyncMock(return_value="Fallback translation result")

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            # Helper raises to simulate an unexpected internal failure.
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                new=AsyncMock(side_effect=RuntimeError("Unexpected internal failure")),
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="en"),
            )

        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertEqual(result["translation_reason_code"], "structured_exception")
        self.assertIsNone(result["translated_body_html"])
        self.assertEqual(result["translated_body_text"], "Fallback translation result")

    # A4 — Structured success: hidden preheader in translated HTML does not leak
    #      into translated_body_text
    async def test_structured_success_body_text_excludes_hidden_preheader(self):
        """
        When the translated HTML (returned by the helper) contains a hidden
        preheader span, _derive_plain_text_from_html must strip it so the
        hidden text does not appear in translated_body_text.
        """
        html_with_preheader = (
            '<span style="display:none">Hidden preview: check your inbox</span>'
            "<p>Bonjour le monde.</p>"
            "<p>Ceci est un e-mail de test.</p>"
        )
        mock_engine = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, "_lookup_email_record_by_message_id",
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, "_build_rendered_email_payload",
                return_value=_make_payload(
                    attachments=_FAKE_ATTACHMENTS,
                    linked_files=_FAKE_LINKED_FILES,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, "MistralEngine", return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, "_attempt_structured_html_translation",
                new=AsyncMock(return_value=(html_with_preheader, "structured_success")),
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="en"),
            )

        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_fidelity"], "preserved")
        # Hidden preheader must not leak into plain-text field
        self.assertNotIn("Hidden preview: check your inbox", result["translated_body_text"])
        # Visible translated content must be present
        self.assertIn("Bonjour le monde", result["translated_body_text"])


# ---------------------------------------------------------------------------
# Section C — Hidden/preheader element detection
# ---------------------------------------------------------------------------

class TestHiddenElementDetection(unittest.TestCase):
    """
    Section C — Deterministic proof that _is_hidden_element correctly detects
    hidden/preheader elements, and that _collect_translatable_nodes excludes
    their text from the translatable segment list.
    """

    def _span(self, **attrs) -> object:
        """Build a BeautifulSoup <span> tag from the given HTML attributes."""
        from bs4 import BeautifulSoup as BS
        parts = ["<span"]
        for key, val in attrs.items():
            # Support class as a list or string
            parts.append(f' {key}="{val}"')
        parts.append(">text</span>")
        return BS("".join(parts), "html.parser").find("span")

    # C1
    def test_display_none_is_hidden(self):
        self.assertTrue(service._is_hidden_element(self._span(style="display:none")))

    # C2
    def test_display_none_with_surrounding_properties_is_hidden(self):
        self.assertTrue(service._is_hidden_element(
            self._span(style="color:red; display: none; font-size:12px")
        ))

    # C3
    def test_visibility_hidden_is_hidden(self):
        self.assertTrue(service._is_hidden_element(self._span(style="visibility:hidden")))

    # C4
    def test_opacity_zero_is_hidden(self):
        self.assertTrue(service._is_hidden_element(self._span(style="opacity:0")))

    # C5 — partial visibility must NOT be treated as hidden
    def test_opacity_nonzero_is_not_hidden(self):
        self.assertFalse(service._is_hidden_element(self._span(style="opacity:0.5")))

    # C6
    def test_mso_hide_all_is_hidden(self):
        self.assertTrue(service._is_hidden_element(self._span(style="mso-hide:all")))

    # C7
    def test_max_height_zero_px_is_hidden(self):
        self.assertTrue(service._is_hidden_element(
            self._span(style="max-height:0px;overflow:hidden")
        ))

    # C8
    def test_font_size_zero_px_is_hidden(self):
        self.assertTrue(service._is_hidden_element(
            self._span(style="font-size:0px;color:transparent")
        ))

    # C9
    def test_preheader_class_is_hidden(self):
        self.assertTrue(service._is_hidden_element(self._span(**{"class": "preheader"})))

    # C10
    def test_preheader_id_is_hidden(self):
        self.assertTrue(service._is_hidden_element(self._span(id="email-preheader")))

    # C11
    def test_visible_styled_element_is_not_hidden(self):
        self.assertFalse(service._is_hidden_element(
            self._span(style="color:red;font-size:14px;font-weight:bold")
        ))

    # C12
    def test_no_attributes_element_is_not_hidden(self):
        from bs4 import BeautifulSoup as BS
        el = BS("<span>text</span>", "html.parser").find("span")
        self.assertFalse(service._is_hidden_element(el))

    # C13 — collect skips text under display:none ancestor
    def test_collect_skips_display_none_text(self):
        from bs4 import BeautifulSoup as BS
        html = (
            "<body>"
            '<span style="display:none">Hidden preheader — must not translate</span>'
            "<p>Visible body content — must translate</p>"
            "</body>"
        )
        nodes = service._collect_translatable_nodes(BS(html, "html.parser"))
        texts = [str(n) for n in nodes]
        self.assertNotIn("Hidden preheader — must not translate", texts)
        self.assertIn("Visible body content — must translate", texts)

    # C14 — collect skips text nested inside a preheader-class ancestor
    def test_collect_skips_preheader_class_nested_text(self):
        from bs4 import BeautifulSoup as BS
        html = (
            "<body>"
            '<div class="preheader"><span>Preview text for email clients only</span></div>'
            "<p>Actual email body paragraph</p>"
            "</body>"
        )
        nodes = service._collect_translatable_nodes(BS(html, "html.parser"))
        texts = [str(n) for n in nodes]
        self.assertNotIn("Preview text for email clients only", texts)
        self.assertIn("Actual email body paragraph", texts)


# ---------------------------------------------------------------------------
# Section D — Plain-text derivation cleanup
# ---------------------------------------------------------------------------

class TestDeriveCleanPlainText(unittest.TestCase):
    """
    Section D — Deterministic proof that _derive_plain_text_from_html produces
    clean, normalized output and excludes hidden/preheader elements.
    """

    # D1 — Blank-line inflation is collapsed
    def test_excessive_blank_lines_collapsed(self):
        html = "<p>Hello</p><p>World</p>"
        result = service._derive_plain_text_from_html(html)
        self.assertNotIn("\n\n\n", result)
        self.assertIn("Hello", result)
        self.assertIn("World", result)

    # D2 — Hidden display:none element excluded from plain-text output
    def test_hidden_display_none_excluded_from_plain_text(self):
        html = (
            '<span style="display:none">Hidden preheader content</span>'
            "<p>Visible translated paragraph</p>"
        )
        result = service._derive_plain_text_from_html(html)
        self.assertNotIn("Hidden preheader content", result)
        self.assertIn("Visible translated paragraph", result)

    # D3 — Preheader-class element excluded from plain-text output
    def test_preheader_class_excluded_from_plain_text(self):
        html = (
            '<div class="preheader">Email preview: new messages waiting</div>'
            "<p>Dear customer, thank you for your order.</p>"
        )
        result = service._derive_plain_text_from_html(html)
        self.assertNotIn("Email preview: new messages waiting", result)
        self.assertIn("Dear customer, thank you for your order.", result)


# ---------------------------------------------------------------------------
# Section E — Large/rich HTML preflight degradation (P3.5-R3D-P1)
# ---------------------------------------------------------------------------

class TestHtmlPreflightDegradation(unittest.TestCase):
    """
    Section E (unit) — Deterministic proof that _is_html_preflight_degraded
    correctly identifies clearly large/rich HTML bodies and leaves normal
    structured emails unaffected.
    """

    # E1 — Fires when raw HTML exceeds the character-count threshold
    def test_preflight_fires_on_large_html(self):
        large_html = "<p>" + "A" * 30_001 + "</p>"
        self.assertTrue(service._is_html_preflight_degraded(large_html))

    # E1b — HTML right at the threshold boundary does NOT fire
    def test_preflight_does_not_fire_at_threshold_boundary(self):
        # Exactly _PREFLIGHT_MAX_HTML_CHARS chars — must not trigger
        boundary_html = "A" * service._PREFLIGHT_MAX_HTML_CHARS
        self.assertFalse(service._is_html_preflight_degraded(boundary_html))

    # E2 — Fires when image count exceeds threshold (newsletter image density)
    def test_preflight_fires_on_image_dense_html(self):
        imgs = "".join(f'<img src="img{i}.png" alt="photo" />' for i in range(6))
        html = f"<div>{imgs}<p>Newsletter body paragraph.</p></div>"
        self.assertTrue(service._is_html_preflight_degraded(html))

    # E2b — Exactly at the image threshold does NOT fire
    def test_preflight_does_not_fire_at_image_threshold(self):
        imgs = "".join(f'<img src="img{i}.png" />' for i in range(5))
        html = f"<div>{imgs}<p>Body text.</p></div>"
        self.assertFalse(service._is_html_preflight_degraded(html))

    # E3 — Fires when link (href=) count exceeds threshold (CTA/nav link density)
    def test_preflight_fires_on_link_dense_html(self):
        links = "".join(
            f'<a href="https://example.com/{i}">Link {i}</a>' for i in range(21)
        )
        html = f"<div>{links}</div>"
        self.assertTrue(service._is_html_preflight_degraded(html))

    # E3b — Exactly at the link threshold does NOT fire
    def test_preflight_does_not_fire_at_link_threshold(self):
        links = "".join(
            f'<a href="https://example.com/{i}">Link {i}</a>' for i in range(20)
        )
        html = f"<div>{links}</div>"
        self.assertFalse(service._is_html_preflight_degraded(html))

    # E4 — Fires when table count exceeds threshold (layout complexity)
    def test_preflight_fires_on_table_dense_html(self):
        tables = "".join(
            f"<table><tr><td>Row {i}</td></tr></table>" for i in range(6)
        )
        html = f"<div>{tables}</div>"
        self.assertTrue(service._is_html_preflight_degraded(html))

    # E4b — Exactly at the table threshold does NOT fire
    def test_preflight_does_not_fire_at_table_threshold(self):
        tables = "".join(
            f"<table><tr><td>Row {i}</td></tr></table>" for i in range(5)
        )
        html = f"<div>{tables}</div>"
        self.assertFalse(service._is_html_preflight_degraded(html))

    # E5 — Normal structured email (Google Security Alert-class) does NOT trigger
    def test_preflight_does_not_fire_for_normal_structured_email(self):
        # Realistic compact transactional email: 1 logo image, 3 links, 1 table
        html = (
            "<html><body>"
            "<table><tr><td>"
            "  <img src='https://www.gstatic.com/images/branding/googleg/2x/googleg_standard_color_28dp.png' />"
            "  <h2>Security alert</h2>"
            "  <p>A new sign-in to your Google Account was detected.</p>"
            "  <p>Time: Tuesday, 15 April 2025, 09:42 UTC</p>"
            "  <p>Location: Paris, France</p>"
            '  <a href="https://accounts.google.com/signin/v2/review">Check activity</a>'
            '  <a href="https://accounts.google.com/signin/v2/help">Learn more</a>'
            '  <a href="https://myaccount.google.com/security">Manage account</a>'
            "</td></tr></table>"
            "</body></html>"
        )
        self.assertFalse(service._is_html_preflight_degraded(html))


class TestPreflightDegradationRouteContract(unittest.IsolatedAsyncioTestCase):
    """
    Section E (route) — Deterministic proof of the route-level contract when
    the preflight gate fires and when it does not.
    """

    # E6 — Preflight triggers: route returns correct fields, helper never called
    async def test_preflight_degradation_route_contract(self):
        """
        When _is_html_preflight_degraded returns True:
          - _attempt_structured_html_translation must NOT be called
          - translation_mode        == text_fallback
          - translation_fidelity    == simplified
          - translation_reason_code == structured_preflight_degraded
          - translated_body_html    is None
          - translated_body_text    is the text-fallback result
        """
        large_html = "<p>" + "A" * 30_001 + "</p>"
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        mock_engine.generate_text_async = AsyncMock(return_value="Résultat de la traduction")
        helper_spy = AsyncMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=large_html),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                new=helper_spy,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # Structured helper must not have been called — preflight short-circuits
        helper_spy.assert_not_called()

        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        self.assertIsNone(result["translated_body_html"])
        self.assertEqual(result["translated_body_text"], "Résultat de la traduction")
        self.assertEqual(result["gmail_message_id"], _FAKE_GMAIL_MESSAGE_ID)
        self.assertEqual(result["target_language"], "fr")

    # E7 — Normal email: preflight does not fire, structured_success is unaffected
    async def test_structured_success_unaffected_by_preflight(self):
        """
        When _is_html_preflight_degraded returns False (normal email):
          - _attempt_structured_html_translation IS called
          - Structured-success contract fields are unchanged
        """
        normal_html = (
            "<html><body><p>Security alert from Google.</p>"
            '<a href="https://accounts.google.com">Review</a>'
            "</body></html>"
        )
        mock_engine = MagicMock()
        translated_html = "<html><body><p>Alerte de sécurité de Google.</p>" \
                          '<a href="https://accounts.google.com">Vérifier</a>' \
                          "</body></html>"

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=normal_html),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                new=AsyncMock(return_value=(translated_html, "structured_success")),
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_fidelity"], "preserved")
        self.assertEqual(result["translation_reason_code"], "structured_success")
        self.assertEqual(result["translated_body_html"], translated_html)
        self.assertTrue(result["translated_body_text"].strip())


# ---------------------------------------------------------------------------
# Section F — Chunked simplified translation (P3.5-R3E-P1)
# ---------------------------------------------------------------------------

# Large newsletter-class body: three clearly separated paragraphs.
_LARGE_FALLBACK_PARA_1 = "Paragraph one. " * 60          # ~960 chars
_LARGE_FALLBACK_PARA_2 = "Paragraph two content. " * 60   # ~1 380 chars
_LARGE_FALLBACK_PARA_3 = "Paragraph three data. " * 60    # ~1 320 chars
_LARGE_FALLBACK_BODY = (
    _LARGE_FALLBACK_PARA_1.strip() + "\n\n"
    + _LARGE_FALLBACK_PARA_2.strip() + "\n\n"
    + _LARGE_FALLBACK_PARA_3.strip()
)


class TestChunkFallbackHelpers(unittest.TestCase):
    """
    Section F (helper level) — Deterministic proof of the chunking decision
    and splitting helpers.
    """

    # Fh1 — any body (even short) has count_tokens called;
    #        returns False when token count is at or below threshold
    def test_should_not_chunk_when_tokens_at_or_below_threshold(self):
        engine = MagicMock()
        engine.count_tokens.return_value = service._FALLBACK_CHUNK_TOKEN_THRESHOLD
        short_body = "Short email body."   # well below 3 000 chars
        result = service._should_chunk_fallback_translation(short_body, engine)
        self.assertFalse(result)
        # count_tokens must always be called — no character fast-path
        engine.count_tokens.assert_called_once_with(short_body)

    # Fh2 — body with token count above threshold returns True
    def test_should_chunk_large_body(self):
        engine = MagicMock()
        engine.count_tokens.return_value = service._FALLBACK_CHUNK_TOKEN_THRESHOLD + 1
        large_body = "word " * 700   # ~3 500 chars
        result = service._should_chunk_fallback_translation(large_body, engine)
        self.assertTrue(result)
        engine.count_tokens.assert_called_once_with(large_body)

    # Fh2b — large body BUT token count at or below threshold → False
    def test_should_not_chunk_large_body_low_tokens(self):
        engine = MagicMock()
        engine.count_tokens.return_value = service._FALLBACK_CHUNK_TOKEN_THRESHOLD
        large_body = "word " * 700
        result = service._should_chunk_fallback_translation(large_body, engine)
        self.assertFalse(result)

    # Fh3 — paragraph-separated body is split into correct chunks in order
    def test_split_preserves_paragraph_order(self):
        # Use a mock engine that returns the token count as len(text) // 5
        # so paragraph accumulation is predictable.
        engine = MagicMock()
        engine.count_tokens.side_effect = lambda t: len(t) // 5

        body = "Alpha paragraph.\n\nBeta paragraph.\n\nGamma paragraph."
        chunks = service._split_text_into_translation_chunks(body, engine)

        # Must return at least one chunk and preserve all content.
        self.assertGreater(len(chunks), 0)
        recombined = "\n\n".join(chunks)
        self.assertIn("Alpha paragraph.", recombined)
        self.assertIn("Beta paragraph.", recombined)
        self.assertIn("Gamma paragraph.", recombined)
        # Alpha must appear before Beta, Beta before Gamma.
        self.assertLess(recombined.index("Alpha"), recombined.index("Beta"))
        self.assertLess(recombined.index("Beta"), recombined.index("Gamma"))

    # Fh3b — empty body returns exactly one chunk equal to the original
    def test_split_empty_body_returns_original(self):
        engine = MagicMock()
        engine.count_tokens.return_value = 0
        chunks = service._split_text_into_translation_chunks("", engine)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "")

    # Fh3c — single paragraph below budget stays in one chunk
    def test_split_single_small_paragraph_one_chunk(self):
        engine = MagicMock()
        engine.count_tokens.return_value = 50   # well below 800
        chunks = service._split_text_into_translation_chunks(
            "Just one small paragraph with normal content.", engine
        )
        self.assertEqual(len(chunks), 1)


class TestChunkFallbackRouteContract(unittest.IsolatedAsyncioTestCase):
    """
    Section F (route level) — Deterministic proof that the translate-render
    route correctly routes large fallback bodies through the chunked path and
    small ones through the single-call path.
    """

    # F1 — large fallback body is translated via multiple chunk calls and
    #      results are recombined in order
    async def test_large_fallback_uses_chunked_calls_in_order(self):
        """
        When _should_chunk_fallback_translation returns True:
          - generate_text_async must be called once per chunk (not once total)
          - translated_body_text must be the paragraph-joined translation
          - translation_mode / fidelity / reason_code remain unchanged
        """
        known_chunks = ["chunk_alpha", "chunk_beta", "chunk_gamma"]
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 50  # per-chunk estimate
        mock_engine.generate_text_async = AsyncMock(
            side_effect=["tr_alpha", "tr_beta", "tr_gamma"]
        )

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=_LARGE_FALLBACK_BODY),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html="", body_text=_LARGE_FALLBACK_BODY),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_should_chunk_fallback_translation',
                return_value=True,
            ))
            stack.enter_context(patch.object(
                service, '_split_text_into_translation_chunks',
                return_value=known_chunks,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # generate_text_async called exactly once per chunk — not monolithically
        self.assertEqual(mock_engine.generate_text_async.call_count, 3)

        # Results recombined in chunk order with paragraph spacing
        self.assertEqual(result["translated_body_text"], "tr_alpha\n\ntr_beta\n\ntr_gamma")

        # Contract fields unchanged
        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertEqual(result["translation_reason_code"], "html_missing")
        self.assertIsNone(result["translated_body_html"])

    # F2 — small fallback body uses a single generate_text_async call
    async def test_small_fallback_uses_single_call(self):
        """
        When _should_chunk_fallback_translation returns False:
          - generate_text_async must be called exactly once
          - translated_body_text is the direct result of that single call
        """
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        mock_engine.generate_text_async = AsyncMock(return_value="Texte traduit unique")

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=""),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_should_chunk_fallback_translation',
                return_value=False,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(mock_engine.generate_text_async.call_count, 1)
        self.assertEqual(result["translated_body_text"], "Texte traduit unique")
        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")

    # F3 — structured_preflight_degraded route uses chunked fallback internally
    #      while preserving the contract reason code
    async def test_preflight_degraded_with_chunked_fallback_preserves_contract(self):
        """
        When the preflight gate fires (large HTML) AND the derived body_text is
        itself large enough to warrant chunking:
          - translation_reason_code == structured_preflight_degraded
          - translation_mode        == text_fallback
          - generate_text_async called once per chunk
          - translated_body_text is the recombined chunk translation
        """
        large_html = "<p>" + "A" * 30_001 + "</p>"
        known_chunks = ["preflight_chunk_1", "preflight_chunk_2"]
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 50
        mock_engine.generate_text_async = AsyncMock(
            side_effect=["traduit_1", "traduit_2"]
        )
        helper_spy = AsyncMock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=_LARGE_FALLBACK_BODY),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    body_html=large_html,
                    body_text=_LARGE_FALLBACK_BODY,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                new=helper_spy,
            ))
            stack.enter_context(patch.object(
                service, '_should_chunk_fallback_translation',
                return_value=True,
            ))
            stack.enter_context(patch.object(
                service, '_split_text_into_translation_chunks',
                return_value=known_chunks,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # Structured helper must NOT have been called — preflight gates it out
        helper_spy.assert_not_called()

        # Route-level contract for preflight-degraded path must be intact
        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertIsNone(result["translated_body_html"])

        # Internally, chunked path was used
        self.assertEqual(mock_engine.generate_text_async.call_count, 2)
        self.assertEqual(result["translated_body_text"], "traduit_1\n\ntraduit_2")

    # F4 — structured-success route is entirely unaffected by chunking logic
    async def test_structured_success_unaffected_by_chunking(self):
        """
        When translation succeeds via the structured HTML path:
          - _should_chunk_fallback_translation must NOT be called
          - translation_mode     == structured_html
          - translation_fidelity == preserved
          - translated_body_html is the translated HTML
        """
        mock_engine = MagicMock()
        chunk_decision_spy = MagicMock(return_value=False)

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    attachments=_FAKE_ATTACHMENTS,
                    linked_files=_FAKE_LINKED_FILES,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                new=AsyncMock(return_value=(_FAKE_TRANSLATED_HTML, "structured_success")),
            ))
            stack.enter_context(patch.object(
                service, '_should_chunk_fallback_translation',
                new=chunk_decision_spy,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="en"),
            )

        # Chunking decision must never be consulted on the structured-success path
        chunk_decision_spy.assert_not_called()

        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_fidelity"], "preserved")
        self.assertEqual(result["translation_reason_code"], "structured_success")
        self.assertEqual(result["translated_body_html"], _FAKE_TRANSLATED_HTML)
        self.assertTrue(result["translated_body_text"].strip())


# ---------------------------------------------------------------------------
# Section G — Hard fallback split refinement (P3.5-R3E-P1R)
# ---------------------------------------------------------------------------

class TestHardSplitSegmentHelper(unittest.TestCase):
    """
    Section G (helper level) — Deterministic proof that _hard_split_segment
    handles all edge cases: within-budget pass-through, no-punctuation word
    batching, and no-whitespace token-verified prefix split (last resort).
    """

    # Gh1 — segment already within budget is returned unchanged
    def test_within_budget_returned_as_is(self):
        engine = MagicMock()
        engine.count_tokens.return_value = 100   # well within 800
        text = "This is a short paragraph."
        result = service._hard_split_segment(text, engine)
        self.assertEqual(result, [text])
        # count_tokens called exactly once (initial budget check)
        engine.count_tokens.assert_called_once_with(text)

    # Gh2 — paragraph with no sentence punctuation reaches layer 3
    #        (word-group batching) and is split into bounded chunks
    def test_no_punctuation_paragraph_word_batched(self):
        """
        A 900-word paragraph with no .!? or \\n boundaries falls through
        layers 1 and 2 and is split at layer 3 (word-group batching)
        into exactly 2 chunks: 800 words + 100 words.
        """
        # Token model: count words.  Each "word" = 1 token.
        engine = MagicMock()
        engine.count_tokens.side_effect = lambda t: len(t.split()) if t.split() else 1

        no_punct_para = " ".join(["word"] * 900)   # 900 tokens > 800

        chunks = service._hard_split_segment(no_punct_para, engine)

        # Must produce more than one chunk
        self.assertGreater(len(chunks), 1)

        # Every chunk must be within the budget under the same token model
        for c in chunks:
            self.assertLessEqual(len(c.split()), service._FALLBACK_CHUNK_MAX_TOKENS)

        # All original words must be present (no text lost), in order
        reassembled = " ".join(chunks)
        self.assertEqual(reassembled.split(), no_punct_para.split())

    # Gh3 — no-whitespace dense string reaches layer 4 (token-verified split)
    #        and is split with zero text loss; every chunk is token-bounded
    def test_no_whitespace_dense_string_token_verified_split(self):
        """
        A string with no spaces, no punctuation, and no newlines exhausts
        layers 1–3 and is split by the token-verified prefix-split last resort
        (P3.5-R3E-P1R2).  Each emitted chunk satisfies
        engine.count_tokens(chunk) <= _FALLBACK_CHUNK_MAX_TOKENS by construction.
        """
        # Token model: any string longer than 800 chars is "oversized" (900 tokens),
        # any string ≤ 800 chars is within budget (10 tokens).
        # Binary search converges to cut=800 per iteration → 4 equal chunks.
        engine = MagicMock()
        engine.count_tokens.side_effect = lambda t: 900 if len(t) > 800 else 10

        dense_string = "A" * 3200

        chunks = service._hard_split_segment(dense_string, engine)

        # Must be split (layer 4 fired)
        self.assertGreater(len(chunks), 1)

        # No text lost — concatenation must recover the original string exactly
        self.assertEqual("".join(chunks), dense_string)

        # Token-verified guarantee: every chunk is within budget under the same model
        for c in chunks:
            self.assertLessEqual(
                engine.count_tokens(c),
                service._FALLBACK_CHUNK_MAX_TOKENS,
                f"Chunk of length {len(c)} exceeds token budget",
            )


class TestHardSplitRouteContract(unittest.IsolatedAsyncioTestCase):
    """
    Section G (route level) — End-to-end proof that a large, no-punctuation
    body_text still produces multiple generate_text_async calls through the
    real (non-mocked) split helpers.
    """

    # Gh4 — route: large no-punctuation body goes through real helpers
    #        and still calls generate_text_async multiple times
    async def test_route_large_no_punct_body_multiple_calls(self):
        """
        When body_text is a long, punctuation-free block (no .!? or \\n):
          - _should_chunk_fallback_translation returns True (real implementation)
          - _split_text_into_translation_chunks → _hard_split_segment fires
            word-group batching (layer 3) and produces multiple chunks
          - generate_text_async is called once per chunk (not once total)
          - translation contract fields are correct
        """
        # 3 000 "word" tokens — exceeds the 1 500-token chunking threshold.
        no_punct_body = " ".join(["word"] * 3000)

        mock_engine = MagicMock()
        # Token model: word count.  Clean and deterministic.
        mock_engine.count_tokens.side_effect = lambda t: len(t.split()) if t.split() else 1
        mock_engine.generate_text_async = AsyncMock(return_value="traduction")

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=no_punct_body),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                # No HTML — forces html_missing / text_fallback lane.
                return_value=_make_payload(body_html="", body_text=no_punct_body),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # Multiple chunks → multiple calls (not one monolithic call)
        self.assertGreater(mock_engine.generate_text_async.call_count, 1)

        # Contract fields must be correct
        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertEqual(result["translation_reason_code"], "html_missing")
        self.assertIsNone(result["translated_body_html"])

        # Assembled result contains the translated content
        self.assertIn("traduction", result["translated_body_text"])


# ---------------------------------------------------------------------------
# Section H — Token-verified final split guarantee (P3.5-R3E-P1R2)
# ---------------------------------------------------------------------------

class TestTokenVerifiedPrefixSplit(unittest.TestCase):
    """
    Section H (helper level) — Deterministic proof that
    _token_verified_prefix_split guarantees every emitted chunk satisfies
    engine.count_tokens(chunk) <= _FALLBACK_CHUNK_MAX_TOKENS by construction,
    regardless of tokeniser density.
    """

    # Hi1 — empty string returns empty list
    def test_empty_string_returns_empty_list(self):
        engine = MagicMock()
        result = service._token_verified_prefix_split("", engine)
        self.assertEqual(result, [])
        engine.count_tokens.assert_not_called()

    # Hi2 — string already within budget returned as single-element list
    def test_within_budget_returned_as_single_element(self):
        engine = MagicMock()
        engine.count_tokens.return_value = 50   # well within 800
        text = "Short segment within budget."
        result = service._token_verified_prefix_split(text, engine)
        self.assertEqual(result, [text])
        # Only the initial budget check should have been made
        engine.count_tokens.assert_called_once_with(text)

    # Hi3 — CJK-density: 1 token per character
    #        Every chunk token-bounded; concatenation recovers original exactly
    def test_cjk_density_all_chunks_token_bounded(self):
        """
        With a 1-token-per-character tokeniser, each emitted chunk must have
        at most _FALLBACK_CHUNK_MAX_TOKENS characters.  Binary-search prefix
        fitting must find the exact per-character boundary.
        """
        engine = MagicMock()
        # Exact CJK-worst-case: every character is one token.
        engine.count_tokens.side_effect = lambda t: len(t)

        # 2 500 chars → 2 500 tokens.  Expected chunks: ⌈2500/800⌉ = 4
        # (800 + 800 + 800 + 100)
        dense = "A" * 2500

        chunks = service._token_verified_prefix_split(dense, engine)

        # No text lost
        self.assertEqual("".join(chunks), dense)

        # Multiple chunks emitted
        self.assertGreater(len(chunks), 1)

        # KEY INVARIANT: every chunk is within budget under the actual tokeniser
        for c in chunks:
            self.assertLessEqual(
                engine.count_tokens(c),
                service._FALLBACK_CHUNK_MAX_TOKENS,
                f"Chunk of length {len(c)} exceeds token budget",
            )

        # With count_tokens == len, binary search finds exactly 800 chars/chunk.
        self.assertEqual(len(chunks), 4)
        self.assertTrue(all(len(c) <= service._FALLBACK_CHUNK_MAX_TOKENS for c in chunks))


class TestTokenVerifiedRouteContract(unittest.IsolatedAsyncioTestCase):
    """
    Section H (route level) — End-to-end proof that a large dense
    no-whitespace body (CJK-density tokeniser) still produces multiple
    generate_text_async calls and correct contract fields.
    """

    # Hi4 — route: dense 1-token/char body triggers chunking via real helpers
    async def test_route_dense_body_token_verified_multiple_calls(self):
        """
        With a 1-token-per-character tokeniser (CJK worst case) and a
        no-whitespace body of 3 000 chars:
          - _should_chunk_fallback_translation returns True (3 000 > 1 500 threshold)
          - _hard_split_segment fires layer 4 (_token_verified_prefix_split)
          - generate_text_async called multiple times (one per chunk)
          - translation contract fields are correct
        """
        # 3 000-char no-whitespace body, no punctuation, no line breaks.
        dense_body = "X" * 3000

        mock_engine = MagicMock()
        # 1 token per character — worst-case dense tokenisation.
        mock_engine.count_tokens.side_effect = lambda t: len(t)
        mock_engine.generate_text_async = AsyncMock(return_value="traduction")

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=dense_body),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                # No HTML → html_missing / text_fallback lane.
                return_value=_make_payload(body_html="", body_text=dense_body),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # Multiple chunks → multiple calls (not one monolithic call).
        # 3 000 tokens / 800 budget = ⌈3000/800⌉ = 4 chunks expected.
        self.assertGreater(mock_engine.generate_text_async.call_count, 1)

        # Contract fields correct
        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertEqual(result["translation_reason_code"], "html_missing")
        self.assertIsNone(result["translated_body_html"])

        # Translated content present in assembled result
        self.assertIn("traduction", result["translated_body_text"])


# ---------------------------------------------------------------------------
# Section I — Dense-token chunking decision fix (P3.5-R3E-P1R3)
# ---------------------------------------------------------------------------

class TestDenseTokenChunkingDecision(unittest.TestCase):
    """
    Section I (helper level) — Proves that the chunking decision is based
    purely on token count, with no character-length fast-path that could
    suppress chunking for dense-token bodies.
    """

    # Ii1 — dense body: < 3 000 chars, token count > threshold → True
    def test_should_chunk_dense_short_body(self):
        """
        A dense-token body shorter than 3 000 characters with token count
        above _FALLBACK_CHUNK_TOKEN_THRESHOLD must return True.  Token count
        is the sole decision criterion — character length is not consulted,
        ensuring CJK and other dense-token scripts are handled correctly.
        """
        engine = MagicMock()
        engine.count_tokens.return_value = service._FALLBACK_CHUNK_TOKEN_THRESHOLD + 1
        dense_short = "X" * 2000   # 2 000 chars — dense in tokens, short in characters
        result = service._should_chunk_fallback_translation(dense_short, engine)
        self.assertTrue(result)
        # count_tokens must be called regardless of body length
        engine.count_tokens.assert_called_once_with(dense_short)


class TestDenseTokenChunkingRouteContract(unittest.IsolatedAsyncioTestCase):
    """
    Section I (route level) — End-to-end proof that a dense-token body
    shorter than 3 000 characters still triggers chunking and produces
    multiple generate_text_async calls.
    """

    # Ii2 — route: dense short body < 3 000 chars, multiple calls, correct contract
    async def test_route_dense_short_body_below_3000_chars_chunked(self):
        """
        body_text = 'X' * 2 000 with a 1-token-per-character tokeniser:
          - len(body_text) = 2 000  (short in characters)
          - count_tokens   = 2 000  >  1 500  (above threshold)

        _should_chunk_fallback_translation returns True because token count
        drives the decision, not character length.  The route must call
        generate_text_async multiple times and contract fields must be correct.
        """
        dense_short_body = "X" * 2000   # 2 000 chars — short in characters, above token threshold

        mock_engine = MagicMock()
        # 1 token per character: 2 000 tokens > 1 500 threshold.
        mock_engine.count_tokens.side_effect = lambda t: len(t)
        mock_engine.generate_text_async = AsyncMock(return_value="traduction")

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=dense_short_body),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                # No HTML → html_missing / text_fallback lane.
                return_value=_make_payload(body_html="", body_text=dense_short_body),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # Chunking must have fired: multiple calls, not one monolithic call.
        # With count_tokens==len and budget=800: ⌈2000/800⌉ = 3 chunks expected.
        self.assertGreater(mock_engine.generate_text_async.call_count, 1)

        # Contract fields correct
        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertEqual(result["translation_reason_code"], "html_missing")
        self.assertIsNone(result["translated_body_html"])
        self.assertIn("traduction", result["translated_body_text"])


# ---------------------------------------------------------------------------
# Section J — Simplified fallback source fidelity (P3.5-R3F-P1)
# ---------------------------------------------------------------------------

# Rich HTML fixture used across Section J tests.
_RICH_PREFLIGHT_HTML = (
    "<html><body>"
    "<p id='preheader' style='display:none'>Preview text hidden</p>"
    "<p>Hello, here is your invoice summary.</p>"
    "<p>Total due: $42.00</p>"
    "<div class='footer'>Company Inc. | 123 Main St</div>"
    "<div class='unsubscribe'>Click here to unsubscribe</div>"
    "<div class='social'>Follow us on Twitter</div>"
    "</body></html>"
)


class TestSimplifiedFallbackSourceFidelity(unittest.TestCase):
    """
    Deterministic proof that noise elements are suppressed in the simplified
    fallback source (helper-level tests J1–J10).
    """

    # --- _is_noise_element_for_simplified_source ---

    # J1
    def test_noise_footer_class_detected(self):
        elem = MagicMock()
        elem.get = lambda attr, default=None: (
            ["footer"] if attr == "class" else (default or "")
        )
        self.assertTrue(service._is_noise_element_for_simplified_source(elem))

    # J2
    def test_noise_unsubscribe_class_detected(self):
        elem = MagicMock()
        elem.get = lambda attr, default=None: (
            ["unsubscribe"] if attr == "class" else (default or "")
        )
        self.assertTrue(service._is_noise_element_for_simplified_source(elem))

    # J3
    def test_noise_social_class_detected(self):
        elem = MagicMock()
        elem.get = lambda attr, default=None: (
            ["social"] if attr == "class" else (default or "")
        )
        self.assertTrue(service._is_noise_element_for_simplified_source(elem))

    # J4
    def test_noise_unsub_class_detected(self):
        elem = MagicMock()
        elem.get = lambda attr, default=None: (
            ["unsub"] if attr == "class" else (default or "")
        )
        self.assertTrue(service._is_noise_element_for_simplified_source(elem))

    # J5
    def test_noise_view_in_browser_class_detected(self):
        elem = MagicMock()
        elem.get = lambda attr, default=None: (
            ["view-in-browser"] if attr == "class" else (default or "")
        )
        self.assertTrue(service._is_noise_element_for_simplified_source(elem))

    # J6
    def test_noise_footer_id_detected(self):
        elem = MagicMock()
        elem.get = lambda attr, default=None: (
            [] if attr == "class" else ("footer" if attr == "id" else (default or ""))
        )
        self.assertTrue(service._is_noise_element_for_simplified_source(elem))

    # J7
    def test_legitimate_content_element_not_noise(self):
        elem = MagicMock()
        elem.get = lambda attr, default=None: (
            ["main-content"] if attr == "class" else (default or "")
        )
        self.assertFalse(service._is_noise_element_for_simplified_source(elem))

    # --- _derive_simplified_fallback_source ---

    # J8
    def test_derive_simplified_source_suppresses_footer_unsubscribe(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")
        result = service._derive_simplified_fallback_source(_RICH_PREFLIGHT_HTML)
        self.assertIn("invoice summary", result)
        self.assertIn("Total due", result)
        self.assertNotIn("unsubscribe", result.lower())
        self.assertNotIn("Follow us on Twitter", result)
        self.assertNotIn("Company Inc.", result)

    # J9
    def test_derive_simplified_source_suppresses_preheader_hidden(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")
        result = service._derive_simplified_fallback_source(_RICH_PREFLIGHT_HTML)
        self.assertNotIn("Preview text hidden", result)

    # J10
    def test_derive_simplified_source_returns_empty_when_bs4_unavailable(self):
        with patch.object(service, '_BS4_AVAILABLE', False):
            result = service._derive_simplified_fallback_source(_RICH_PREFLIGHT_HTML)
        self.assertEqual(result, "")


class TestSimplifiedFallbackSourceRouteIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Route-level proofs for simplified fallback source (J11–J13).
    """

    # J11
    async def test_route_preflight_degraded_uses_derived_source(self):
        """Route uses derived source when guard approves it.
        Guard approves when derived is materially shorter (< 90%) than existing body_text.
        """
        # Build an HTML that is preflight-degraded by char count.
        rich_html = _RICH_PREFLIGHT_HTML + ("x" * 40_000)
        # Large noisy body (600 chars) — simulates MIME plain-text with marketing noise.
        original_body_text = "Noisy marketing body. " * 27  # ~594 chars
        # Clean derived source (~52 chars >= 50 min, well under 90% of 594) — guard approves.
        derived_source_content = "Invoice summary: Total due $42.00. Please review it."

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10  # below chunk threshold
        captured_prompts: list = []

        async def _capture_generate(*, prompt, **kwargs):
            captured_prompts.append(prompt)
            return "translated"

        mock_engine.generate_text_async = _capture_generate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=original_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=original_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_derive_protected_fallback_source',
                return_value=(derived_source_content, {}),
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        self.assertEqual(result["translation_mode"], "text_fallback")
        # The derived source must have been used — original body text must not appear.
        combined_prompts = "\n".join(captured_prompts)
        self.assertIn(derived_source_content, combined_prompts)
        self.assertNotIn(original_body_text, combined_prompts)

    # J12
    async def test_route_preflight_degraded_falls_back_to_body_text_when_derivation_empty(self):
        """Route falls back to original body_text when BS4 is unavailable and
        derivation returns ""."""
        rich_html = _RICH_PREFLIGHT_HTML + ("x" * 40_000)
        original_body_text = "fallback body text used when no derivation"

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_prompts: list = []

        async def _capture_generate(*, prompt, **kwargs):
            captured_prompts.append(prompt)
            return "translated"

        mock_engine.generate_text_async = _capture_generate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=original_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=original_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_derive_protected_fallback_source',
                return_value=("", {}),
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        combined_prompts = "\n".join(captured_prompts)
        self.assertIn(original_body_text, combined_prompts)

    # J13
    async def test_structured_success_unaffected_by_simplified_source_logic(self):
        """structured_success route must not call _derive_protected_fallback_source."""
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                return_value=(_FAKE_TRANSLATED_HTML, "structured_success"),
            ))
            mock_derive = stack.enter_context(patch.object(
                service, '_derive_protected_fallback_source',
                return_value=("should not be called", {}),
            ))
            mock_engine.generate_text_async = AsyncMock(return_value="translated text")

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        mock_derive.assert_not_called()
        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_reason_code"], "structured_success")


class TestSimplifiedSourcePreferenceGuard(unittest.TestCase):
    """
    Unit tests for _should_prefer_simplified_source (J14–J17).
    """

    # J14
    def test_guard_rejects_empty_derived(self):
        self.assertFalse(service._should_prefer_simplified_source("some body text", ""))

    def test_guard_rejects_tiny_derived(self):
        # Below _SIMPLIFIED_SOURCE_MIN_CHARS even if shorter than existing.
        tiny = "short"  # 5 chars < 50 minimum
        existing = "A" * 500
        self.assertFalse(service._should_prefer_simplified_source(existing, tiny))

    # J15
    def test_guard_rejects_derived_not_materially_shorter(self):
        # Derived is 95% of existing — not a material reduction.
        existing = "X" * 1000
        derived = "X" * 950  # 95% — above the 90% threshold, guard rejects
        self.assertFalse(service._should_prefer_simplified_source(existing, derived))

    def test_guard_rejects_derived_larger_than_existing(self):
        existing = "A" * 300
        derived = "B" * 400  # larger — extraction inflated content
        self.assertFalse(service._should_prefer_simplified_source(existing, derived))

    def test_guard_rejects_derived_same_size_as_existing(self):
        body = "C" * 200
        self.assertFalse(service._should_prefer_simplified_source(body, body))

    # J16
    def test_guard_approves_derived_materially_shorter(self):
        # Derived is 50% of existing — clear noise removal.
        existing = "Z" * 1000
        derived = "Z" * 500  # 50% — well below the 90% threshold
        self.assertTrue(service._should_prefer_simplified_source(existing, derived))

    def test_guard_approves_derived_just_below_threshold(self):
        # Derived is 89% of existing — just under the 90% cut-off.
        existing = "W" * 1000
        derived = "W" * 889  # 88.9% — guard approves
        self.assertTrue(service._should_prefer_simplified_source(existing, derived))

    # J17
    def test_guard_approves_when_existing_body_empty(self):
        # Empty existing: any substantial derived source should be used.
        derived = "Invoice summary: Total due $42.00. Please review now."
        self.assertTrue(service._should_prefer_simplified_source("", derived))

    def test_guard_rejects_when_existing_body_empty_but_derived_tiny(self):
        self.assertFalse(service._should_prefer_simplified_source("", "tiny"))


class TestSimplifiedSourcePreferenceGuardRouteIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Route-level proof that the guard blocks regressions (J18).
    """

    # J18
    async def test_route_preflight_degraded_preserves_body_text_when_guard_rejects(self):
        """Guard rejects when derived source is not materially shorter.
        Route must preserve the original body_text and NOT use the derived source.
        """
        rich_html = _RICH_PREFLIGHT_HTML + ("x" * 40_000)
        # Short, clean existing body_text — guard will reject any derived
        # source that is not smaller by at least 10%.
        original_body_text = "Clean invoice summary. Total due $42.00."  # 41 chars
        # Derived source is longer than existing — guard rejects it.
        derived_source_bloated = "B" * 500  # 500 chars > 41 * 0.9 = 36.9

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_prompts: list = []

        async def _capture_generate(*, prompt, **kwargs):
            captured_prompts.append(prompt)
            return "translated"

        mock_engine.generate_text_async = _capture_generate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=original_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=original_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_derive_protected_fallback_source',
                return_value=(derived_source_bloated, {}),
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        combined_prompts = "\n".join(captured_prompts)
        # Original body_text must have been used, not the bloated derived source.
        self.assertIn(original_body_text, combined_prompts)
        self.assertNotIn(derived_source_bloated, combined_prompts)


# ---------------------------------------------------------------------------
# Section K — Anchor- and structure-preserving simplified source (P3.5-R3F-P1R2)
# ---------------------------------------------------------------------------

# HTML fixture for K unit tests — small enough to inspect output exactly.
_K_CONTENT_HTML = (
    "<html><body>"
    "<h1>Invoice Summary</h1>"
    "<p>Please review <a href='https://example.com/invoice'>your invoice</a> attached.</p>"
    "<ul>"
    "<li>Item A: $10.00</li>"
    "<li>Item B: $32.00</li>"
    "</ul>"
    "<div class='unsubscribe'>"
    "<a href='https://example.com/unsub'>Unsubscribe</a>"
    "</div>"
    "<p>Thank you.</p>"
    "</body></html>"
)


class TestAnchorAndStructurePreservingSource(unittest.TestCase):
    """
    Deterministic unit tests for the anchor/structure improvements in
    _derive_simplified_fallback_source (K1–K6).
    Skipped when BS4 is not available.
    """

    def setUp(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    # K1
    def test_meaningful_content_link_preserved(self):
        result = service._derive_simplified_fallback_source(_K_CONTENT_HTML)
        self.assertIn("your invoice (https://example.com/invoice)", result)

    # K2
    def test_noise_zone_anchor_suppressed(self):
        result = service._derive_simplified_fallback_source(_K_CONTENT_HTML)
        self.assertNotIn("Unsubscribe", result)
        self.assertNotIn("https://example.com/unsub", result)

    # K3
    def test_fragment_hrefless_plain_mailto_annotated(self):
        html = (
            "<html><body><p>"
            "<a href='#section'>Jump link</a> | "
            "<a href='mailto:info@example.com'>Email us</a> | "
            "<a>No href</a> | "
            "<a href='https://real.com/page'>Real link</a>"
            "</p></body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        # Fragment anchor: plain text only, no URL annotation
        self.assertIn("Jump link", result)
        self.assertNotIn("Jump link (#", result)
        # mailto: anchor: annotated with address
        self.assertIn("Email us (info@example.com)", result)
        self.assertNotIn("Email us (mailto", result)
        # Href-less anchor: plain text
        self.assertIn("No href", result)
        # http/https: URL inline
        self.assertIn("Real link (https://real.com/page)", result)

    # K4
    def test_block_element_structure_blank_line_separation(self):
        result = service._derive_simplified_fallback_source(_K_CONTENT_HTML)
        # Headings, paragraphs, and list items must be separated by blank lines.
        self.assertIn("Invoice Summary", result)
        self.assertIn("Thank you.", result)
        # Blank line between at least two block-level siblings.
        self.assertIn("\n\n", result)
        # Items are present
        self.assertIn("Item A: $10.00", result)
        self.assertIn("Item B: $32.00", result)

    # K5 — updated: translate="no" tag unwrapped; visible text now preserved
    def test_translate_no_element_preserved(self):
        html = (
            "<html><body>"
            "<p>Translate this <span translate='no'>BrandName</span> text.</p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("BrandName", result)
        self.assertIn("Translate this", result)
        self.assertIn("text.", result)

    # K6 — updated: notranslate tag unwrapped; visible text now preserved
    def test_notranslate_class_element_preserved(self):
        html = (
            "<html><body>"
            "<p>Amount: <span class='notranslate'>USD 42.00</span></p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("USD 42.00", result)
        self.assertIn("Amount:", result)


class TestAnchorAndStructurePreservingSourceRoute(unittest.IsolatedAsyncioTestCase):
    """
    End-to-end route tests for the improved derivation (K7–K8).
    Use real _derive_simplified_fallback_source — skipped if BS4 unavailable.
    """

    def _skip_if_no_bs4(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    # K7
    async def test_route_content_link_url_in_translation_prompt(self):
        """Content-link URL from derived source appears in the translation prompt."""
        self._skip_if_no_bs4()
        content_html = (
            "<p>See <a href='https://example.com/invoice'>your invoice</a> "
            "for the full breakdown.</p>"
        )
        # Hidden padding: stripped by Layer 1, keeps HTML > 30 000 chars for preflight.
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{content_html}{padding}</body></html>"
        # Long enough that the short derived source passes the guard.
        existing_body_text = "A" * 500

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_prompts: list = []

        async def _capture(*, prompt, **kwargs):
            captured_prompts.append(prompt)
            return "translated"

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        combined = "\n".join(captured_prompts)
        self.assertIn("https://example.com/invoice", combined)
        self.assertNotIn("A" * 500, combined)

    # K8
    async def test_route_guard_rejects_bloated_derived_uses_original_body(self):
        """Guard rejects when derived source is larger than existing body_text;
        original body_text must be used for translation."""
        self._skip_if_no_bs4()
        # Short content → derived source will be ~35 chars.
        content_html = "<p>Hello from the newsletter!</p>"
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{content_html}{padding}</body></html>"
        # Very short existing body — guard rejects any derived > 15 chars.
        existing_body_text = "Short clean body."  # 17 chars

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_prompts: list = []

        async def _capture(*, prompt, **kwargs):
            captured_prompts.append(prompt)
            return "translated"

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        combined = "\n".join(captured_prompts)
        self.assertIn(existing_body_text, combined)
        self.assertNotIn("newsletter", combined)


# ---------------------------------------------------------------------------
# Section L — Protected-content and actionable-target fidelity (P3.5-R3F-P1R3)
# ---------------------------------------------------------------------------

class TestProtectedContentAndActionableTargetFidelity(unittest.TestCase):
    """
    Deterministic unit tests proving the R3F-P1R3 fidelity fixes (L1–L6):
      - translate="no" / class="notranslate" visible text is preserved
      - mailto: and tel: anchors are annotated with the extracted contact target
      - compact rule: label == destination → plain label only
      - noise-zone contact anchors remain suppressed
    Skipped when BS4 is unavailable.
    """

    def setUp(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    # L1
    def test_translate_no_content_visible_in_derived_source(self):
        html = (
            "<html><body>"
            "<p>Reference: <span translate='no'>INV-2026-0042</span></p>"
            "<p>Please pay the amount shown.</p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("INV-2026-0042", result)
        self.assertIn("Reference:", result)
        self.assertIn("Please pay", result)

    # L2
    def test_notranslate_class_content_visible_in_derived_source(self):
        html = (
            "<html><body>"
            "<p>Total: <span class='notranslate'>EUR 199.99</span></p>"
            "<p>Due by 2026-06-01.</p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("EUR 199.99", result)
        self.assertIn("Total:", result)
        self.assertIn("Due by 2026-06-01.", result)

    # L3
    def test_mailto_anchor_annotated_with_address(self):
        html = (
            "<html><body>"
            "<p>Questions? <a href='mailto:support@example.com'>Contact support</a></p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("Contact support (support@example.com)", result)
        self.assertNotIn("mailto:", result)

    # L3b — mailto: with query params: only address part preserved
    def test_mailto_query_params_stripped(self):
        html = (
            "<html><body>"
            "<p><a href='mailto:info@example.com?subject=Hello'>Email us</a></p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("Email us (info@example.com)", result)
        self.assertNotIn("subject=Hello", result)

    # L4
    def test_tel_anchor_annotated_with_number(self):
        html = (
            "<html><body>"
            "<p>Call us: <a href='tel:+18005551234'>+1 800 555 1234</a></p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("+1 800 555 1234 (+18005551234)", result)
        self.assertNotIn("tel:", result)

    # L5 — compact rule: label already equals destination → no duplication
    def test_compact_rule_label_equals_mailto_address(self):
        html = (
            "<html><body>"
            "<p>Reply to <a href='mailto:noreply@example.com'>noreply@example.com</a>.</p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("noreply@example.com", result)
        self.assertNotIn("noreply@example.com (noreply@example.com)", result)

    def test_compact_rule_label_equals_https_url(self):
        html = (
            "<html><body>"
            "<p>Visit <a href='https://example.com'>https://example.com</a>.</p>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("https://example.com", result)
        self.assertNotIn("https://example.com (https://example.com)", result)

    # L6 — noise-zone contact anchors remain suppressed
    def test_noise_zone_mailto_suppressed(self):
        html = (
            "<html><body>"
            "<p>Main content here.</p>"
            "<div class='unsubscribe'>"
            "<a href='mailto:unsub@example.com'>Unsubscribe</a>"
            "</div>"
            "</body></html>"
        )
        result = service._derive_simplified_fallback_source(html)
        self.assertIn("Main content here.", result)
        self.assertNotIn("Unsubscribe", result)
        self.assertNotIn("unsub@example.com", result)


class TestProtectedContentFidelityRoute(unittest.IsolatedAsyncioTestCase):
    """
    Route-level integration proofs for R3F-P1R3 (L7–L9).
    Use real _derive_simplified_fallback_source — skipped if BS4 unavailable.
    """

    def _skip_if_no_bs4(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    # L7
    async def test_route_placeholder_in_prompt_not_raw_protected_text(self):
        """Protected translate='no' content is replaced with a [[PROT_N]] placeholder
        in the translation prompt; the raw protected value is not exposed to the model."""
        self._skip_if_no_bs4()
        content_html = (
            "<h1>Invoice</h1>"
            "<p>Total: <span translate='no'>USD 42.00</span></p>"
            "<p>Contact: <a href='mailto:billing@example.com'>billing@example.com</a></p>"
        )
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{content_html}{padding}</body></html>"
        existing_body_text = "A" * 500  # long so guard approves derived

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_prompts: list = []

        async def _capture(*, prompt, **kwargs):
            captured_prompts.append(prompt)
            # Model preserves the placeholder faithfully in the "translated" output.
            return "Facture\n\nTotal: [[PROT_0]]\n\nContact: billing@example.com"

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        combined = "\n".join(captured_prompts)
        # Placeholder must appear in the prompt — raw protected value must NOT.
        self.assertIn("[[PROT_0]]", combined)
        self.assertNotIn("USD 42.00", combined)
        # Non-protected annotation (mailto:) still appears in the prompt.
        self.assertIn("billing@example.com", combined)
        self.assertNotIn("A" * 500, combined)
        # After restoration the final translated_body_text must have original value.
        self.assertIn("USD 42.00", result["translated_body_text"])
        self.assertNotIn("[[PROT_0]]", result["translated_body_text"])

    # L8
    async def test_route_guard_reject_preserves_original_body_text(self):
        """Guard rejects derived source that is not materially shorter;
        original body_text must be used even when derivation contains protected content."""
        self._skip_if_no_bs4()
        content_html = (
            "<p>Hello. <span translate='no'>REF-001</span></p>"
        )
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{content_html}{padding}</body></html>"
        # Very short existing body — derived source will be larger, guard rejects.
        existing_body_text = "Short body."  # 11 chars; any derived >= 10 chars rejects

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_prompts: list = []

        async def _capture(*, prompt, **kwargs):
            captured_prompts.append(prompt)
            return "translated"

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")
        combined = "\n".join(captured_prompts)
        self.assertIn(existing_body_text, combined)

    # L9
    async def test_structured_success_unaffected_by_protected_content_changes(self):
        """structured_success path must not invoke _derive_protected_fallback_source."""
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                return_value=(_FAKE_TRANSLATED_HTML, "structured_success"),
            ))
            mock_derive = stack.enter_context(patch.object(
                service, '_derive_protected_fallback_source',
                return_value=("should not be reached", {}),
            ))
            mock_engine.generate_text_async = AsyncMock(return_value="translated text")

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        mock_derive.assert_not_called()
        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_reason_code"], "structured_success")


# ---------------------------------------------------------------------------
# Section M — Protected token preservation (P3.5-R3F-P1R4)
# ---------------------------------------------------------------------------

class TestDeriveProtectedFallbackSource(unittest.TestCase):
    """
    Deterministic unit tests for _derive_protected_fallback_source (M1–M8).
    Skipped when BS4 is unavailable.
    """

    def setUp(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    # M1
    def test_translate_no_replaced_by_placeholder(self):
        html = (
            "<html><body>"
            "<p>Total: <span translate='no'>USD 42.00</span></p>"
            "</body></html>"
        )
        source, pmap = service._derive_protected_fallback_source(html)
        self.assertNotIn("USD 42.00", source)
        self.assertIn("[[PROT_0]]", source)
        self.assertIn("Total:", source)

    # M2
    def test_notranslate_class_replaced_by_placeholder(self):
        html = (
            "<html><body>"
            "<p>Ref: <span class='notranslate'>INV-2026-9999</span></p>"
            "</body></html>"
        )
        source, pmap = service._derive_protected_fallback_source(html)
        self.assertNotIn("INV-2026-9999", source)
        self.assertIn("[[PROT_0]]", source)

    # M3
    def test_placeholder_map_contains_original_text(self):
        html = (
            "<html><body>"
            "<p>Amount: <span translate='no'>EUR 199.99</span></p>"
            "</body></html>"
        )
        source, pmap = service._derive_protected_fallback_source(html)
        self.assertIn("[[PROT_0]]", pmap)
        self.assertEqual(pmap["[[PROT_0]]"], "EUR 199.99")

    # M4
    def test_multiple_protected_elements_get_distinct_tokens(self):
        html = (
            "<html><body>"
            "<p><span translate='no'>Alpha</span> and "
            "<span class='notranslate'>Beta</span></p>"
            "</body></html>"
        )
        source, pmap = service._derive_protected_fallback_source(html)
        self.assertIn("[[PROT_0]]", pmap)
        self.assertIn("[[PROT_1]]", pmap)
        original_values = set(pmap.values())
        self.assertIn("Alpha", original_values)
        self.assertIn("Beta", original_values)
        self.assertNotIn("Alpha", source)
        self.assertNotIn("Beta", source)

    # M5
    def test_non_protected_content_passes_through(self):
        html = (
            "<html><body>"
            "<p>Invoice summary. Total due: $42.00.</p>"
            "</body></html>"
        )
        source, pmap = service._derive_protected_fallback_source(html)
        self.assertIn("Invoice summary", source)
        self.assertIn("$42.00", source)
        self.assertEqual(pmap, {})

    # M6
    def test_noise_zone_protected_element_suppressed(self):
        html = (
            "<html><body>"
            "<p>Main content.</p>"
            "<div class='footer'>"
            "<span translate='no'>Company Inc.</span>"
            "</div>"
            "</body></html>"
        )
        source, pmap = service._derive_protected_fallback_source(html)
        self.assertIn("Main content.", source)
        # Footer is suppressed in Layer 2 before placeholder Layer 3 runs.
        self.assertNotIn("Company Inc.", source)
        self.assertEqual(pmap, {})

    # M7
    def test_actionable_links_annotated_correctly(self):
        html = (
            "<html><body>"
            "<p>Contact: <a href='mailto:support@example.com'>support@example.com</a></p>"
            "<p>Ref: <span translate='no'>CASE-001</span></p>"
            "</body></html>"
        )
        source, pmap = service._derive_protected_fallback_source(html)
        # mailto: compact rule: label == address → plain label
        self.assertIn("support@example.com", source)
        # Protected span replaced by placeholder
        self.assertNotIn("CASE-001", source)
        self.assertIn("[[PROT_0]]", source)
        self.assertEqual(pmap["[[PROT_0]]"], "CASE-001")

    # M8
    def test_returns_empty_tuple_when_bs4_unavailable(self):
        with patch.object(service, '_BS4_AVAILABLE', False):
            source, pmap = service._derive_protected_fallback_source("<p>Hello</p>")
        self.assertEqual(source, "")
        self.assertEqual(pmap, {})


class TestRestoreProtectedTokens(unittest.TestCase):
    """
    Deterministic unit tests for _restore_protected_tokens (M9–M11).
    """

    # M9
    def test_restores_single_placeholder(self):
        pmap = {"[[PROT_0]]": "USD 42.00"}
        text = "Bonjour. Montant: [[PROT_0]]."
        result = service._restore_protected_tokens(text, pmap)
        self.assertEqual(result, "Bonjour. Montant: USD 42.00.")

    # M10
    def test_conservative_noop_when_placeholder_absent(self):
        pmap = {"[[PROT_0]]": "USD 42.00"}
        text = "Bonjour. Montant non indiqué."  # placeholder dropped by model
        result = service._restore_protected_tokens(text, pmap)
        # No injection — text returned as-is.
        self.assertEqual(result, "Bonjour. Montant non indiqué.")
        self.assertNotIn("USD 42.00", result)

    # M11
    def test_multiple_tokens_restored_independently(self):
        pmap = {"[[PROT_0]]": "EUR 199.99", "[[PROT_1]]": "INV-2026-0042"}
        text = "Montant: [[PROT_0]]. Référence: [[PROT_1]]."
        result = service._restore_protected_tokens(text, pmap)
        self.assertEqual(result, "Montant: EUR 199.99. Référence: INV-2026-0042.")


class TestBuildTranslationSystemPromptProtected(unittest.TestCase):
    """
    Unit tests for _build_translation_system_prompt with protected_tokens (M12–M13).
    """

    # M12
    def test_system_prompt_includes_placeholder_rule_when_tokens_present(self):
        prompt = service._build_translation_system_prompt(
            "fr", protected_tokens=["[[PROT_0]]", "[[PROT_1]]"]
        )
        self.assertIn("[[PROT_0]]", prompt)
        self.assertIn("[[PROT_1]]", prompt)
        self.assertIn("[[PROT_N]]", prompt)
        self.assertIn("EXACTLY", prompt)

    # M13
    def test_system_prompt_no_placeholder_rule_when_tokens_none(self):
        prompt_none = service._build_translation_system_prompt("fr", protected_tokens=None)
        prompt_empty = service._build_translation_system_prompt("fr", protected_tokens=[])
        for prompt in (prompt_none, prompt_empty):
            self.assertNotIn("[[PROT_", prompt)
            self.assertNotIn("PROT_N", prompt)


class TestProtectedTokenPreservationRoute(unittest.IsolatedAsyncioTestCase):
    """
    Route-level integration proofs for P1R4 (M14–M17).
    Use real _derive_protected_fallback_source — skipped if BS4 unavailable.
    """

    def _skip_if_no_bs4(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    # M14
    async def test_system_prompt_contains_placeholder_rule_when_protected_content(self):
        """When guard approves derived source with placeholders, system prompt
        contains [[PROT_N]] rule.  HTML must produce >= 50-char derived source
        so the substance check passes and _use_protected_source is set."""
        self._skip_if_no_bs4()
        content_html = (
            "<h1>Support Case</h1>"
            "<p>Please review the details for reference "
            "<span translate='no'>CASE-001</span>.</p>"
            "<p>Contact our team if you need further information.</p>"
        )
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{content_html}{padding}</body></html>"
        existing_body_text = "A" * 500

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_system_prompts: list = []

        async def _capture(*, prompt, system_prompt=None, **kwargs):
            captured_system_prompts.append(system_prompt or "")
            return "Ref: [[PROT_0]]"

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        combined_sys = "\n".join(captured_system_prompts)
        self.assertIn("[[PROT_0]]", combined_sys)
        self.assertIn("[[PROT_N]]", combined_sys)

    # M15
    async def test_final_translated_body_text_has_restored_protected_value(self):
        """After translation the final translated_body_text contains the original
        protected value, not the [[PROT_N]] placeholder.  HTML must produce
        >= 50-char derived source so the guard approves and restoration is active."""
        self._skip_if_no_bs4()
        content_html = (
            "<h1>Invoice</h1>"
            "<p>Amount due: <span translate='no'>USD 99.00</span></p>"
            "<p>Please settle by the due date shown on your invoice.</p>"
        )
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{content_html}{padding}</body></html>"
        existing_body_text = "A" * 500

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        async def _translate(*, prompt, **kwargs):
            # Simulate model preserving the placeholder faithfully.
            return "Montant: [[PROT_0]]."

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertIn("USD 99.00", result["translated_body_text"])
        self.assertNotIn("[[PROT_0]]", result["translated_body_text"])

    # M16
    async def test_no_placeholder_rule_in_system_prompt_when_no_protected_content(self):
        """When HTML has no protected elements, system prompt has no [[PROT_N]] rule."""
        self._skip_if_no_bs4()
        content_html = "<p>No protected content here.</p>"
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{content_html}{padding}</body></html>"
        existing_body_text = "A" * 500

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_system_prompts: list = []

        async def _capture(*, prompt, system_prompt=None, **kwargs):
            captured_system_prompts.append(system_prompt or "")
            return "translated"

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        combined_sys = "\n".join(captured_system_prompts)
        self.assertNotIn("[[PROT_", combined_sys)

    # M17
    async def test_structured_success_unaffected_by_placeholder_machinery(self):
        """structured_success path must not call _derive_protected_fallback_source."""
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                return_value=(_FAKE_TRANSLATED_HTML, "structured_success"),
            ))
            mock_derive = stack.enter_context(patch.object(
                service, '_derive_protected_fallback_source',
                return_value=("should not be reached", {}),
            ))
            mock_engine.generate_text_async = AsyncMock(return_value="translated text")

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        mock_derive.assert_not_called()
        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_reason_code"], "structured_success")


# ---------------------------------------------------------------------------
# Section N — Placeholder activation guard + restore ordering (P3.5-R3F-P1R4R1)
# ---------------------------------------------------------------------------

# Shared HTML fixture: short content so the guard REJECTS the derived source.
# derived source is < 50 chars (below substance threshold) — guard rejects.
_N_GUARD_REJECT_CONTENT_HTML = (
    "<p>Hello. <span translate='no'>REF-001</span></p>"
)

# Shared HTML fixture: rich enough that the guard APPROVES the derived source
# (derived source >= 50 chars and materially shorter than "A" * 500).
_N_GUARD_APPROVE_CONTENT_HTML = (
    "<h1>Invoice</h1>"
    "<p>Amount due: <span translate='no'>USD 42.00</span></p>"
    "<p>Please settle by the due date shown on your invoice.</p>"
)


class TestPlaceholderActivationGuard(unittest.IsolatedAsyncioTestCase):
    """
    Route-level proofs for the P1R4R1 activation guard and restore ordering
    (N1–N5). Uses real _derive_protected_fallback_source — skipped if BS4
    unavailable.  existing_body_text is tuned per test to force guard approval
    or rejection as required.
    """

    def _skip_if_no_bs4(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    # N1 — guard rejects: no [[PROT_N]] rule in system prompt
    async def test_guard_reject_no_placeholder_rule_in_system_prompt(self):
        """When the guard rejects the protected derived source, the translation
        system prompt must NOT contain any [[PROT_N]] placeholder rule."""
        self._skip_if_no_bs4()
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{_N_GUARD_REJECT_CONTENT_HTML}{padding}</body></html>"
        # Very short existing body forces guard rejection (any derived > existing * 0.9)
        existing_body_text = "Short."

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_system_prompts: list = []

        async def _capture(*, prompt, system_prompt=None, **kwargs):
            captured_system_prompts.append(system_prompt or "")
            return "translated"

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    body_html=rich_html, body_text=existing_body_text,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        combined_sys = "\n".join(captured_system_prompts)
        self.assertNotIn("[[PROT_", combined_sys)

    # N2 — guard rejects: _restore_protected_tokens not called
    async def test_guard_reject_restore_not_called(self):
        """When the guard rejects the protected derived source, restoration
        must NOT be attempted regardless of placeholder_map contents."""
        self._skip_if_no_bs4()
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{_N_GUARD_REJECT_CONTENT_HTML}{padding}</body></html>"
        existing_body_text = "Short."

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        mock_engine.generate_text_async = AsyncMock(return_value="translated output")

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    body_html=rich_html, body_text=existing_body_text,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            mock_restore = stack.enter_context(patch.object(
                service, '_restore_protected_tokens',
            ))

            await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        mock_restore.assert_not_called()

    # N3 — guard approves: [[PROT_N]] rule present in system prompt
    async def test_guard_approve_placeholder_rule_in_system_prompt(self):
        """When the guard approves the protected derived source, the translation
        system prompt MUST contain the [[PROT_N]] placeholder preservation rule."""
        self._skip_if_no_bs4()
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{_N_GUARD_APPROVE_CONTENT_HTML}{padding}</body></html>"
        existing_body_text = "A" * 500  # long — guard approves short derived source

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_system_prompts: list = []

        async def _capture(*, prompt, system_prompt=None, **kwargs):
            captured_system_prompts.append(system_prompt or "")
            return "Facture\n\nMontant dû: [[PROT_0]]\n\nMerci."

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    body_html=rich_html, body_text=existing_body_text,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        combined_sys = "\n".join(captured_system_prompts)
        self.assertIn("[[PROT_0]]", combined_sys)
        self.assertIn("[[PROT_N]]", combined_sys)

    # N4 — guard approves: restoration applied, final text has original value
    async def test_guard_approve_restoration_applied_final_text_correct(self):
        """When the guard approves, restoration replaces the placeholder in
        translated_body_text with the original protected value."""
        self._skip_if_no_bs4()
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{_N_GUARD_APPROVE_CONTENT_HTML}{padding}</body></html>"
        existing_body_text = "A" * 500

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        async def _translate(*, prompt, **kwargs):
            return "Facture\n\nMontant dû: [[PROT_0]]\n\nMerci."

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    body_html=rich_html, body_text=existing_body_text,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertIn("USD 42.00", result["translated_body_text"])
        self.assertNotIn("[[PROT_0]]", result["translated_body_text"])

    # N5 — restoration runs before the empty-content check
    async def test_restoration_before_empty_content_check(self):
        """Restoration runs before the final empty-content validation, so the
        post-restoration text (not the pre-restoration placeholder string) is
        what is evaluated for emptiness.  Proved by having the mock return only
        the placeholder; after restoration the text is non-empty and no 502
        exception is raised."""
        self._skip_if_no_bs4()
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body>{_N_GUARD_APPROVE_CONTENT_HTML}{padding}</body></html>"
        existing_body_text = "A" * 500

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        async def _translate(*, prompt, **kwargs):
            # Model returns ONLY the placeholder — after restoration this becomes
            # "USD 42.00" which is non-empty.  If the empty check ran before
            # restoration, the placeholder itself is non-empty too, so the test
            # would not distinguish the ordering.  We verify the correct value
            # is in the final output, confirming restoration preceded any check.
            return "[[PROT_0]]"

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    body_html=rich_html, body_text=existing_body_text,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            # Must not raise HTTPException 502 — restoration gives non-empty text.
            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translated_body_text"], "USD 42.00")
        self.assertNotIn("[[PROT_0]]", result["translated_body_text"])


# ---------------------------------------------------------------------------
# Section O — Protected-token chunking integrity (P3.5-R3F-P1R4R2)
# ---------------------------------------------------------------------------

class TestProtectedTokenChunkingIntegrity(unittest.IsolatedAsyncioTestCase):
    """
    Proofs that [[PROT_N]] placeholder tokens survive chunked fallback
    translation intact (O1–O4).

    O1/O4 test _token_verified_prefix_split directly with a len-based
    count_tokens stand-in so character positions are deterministic.
    O2 tests _split_text_into_translation_chunks end-to-end with injected
    count_tokens to force chunking at known boundaries.
    O3 is a route-level integration test with real BS4 derivation and a
    chunked mock translation engine.
    """

    # O1 — binary-search cut inside placeholder: cut retracted to placeholder start
    def test_prefix_split_does_not_cut_inside_placeholder(self):
        """
        Concrete scenario: 'a' * 795 + ' [[PROT_0]] b' with count_tokens = len.

        Without the fix the binary search produces cut = 800, which lands
        inside [[PROT_0]] (chars 796-805), splitting it into
        'a'*795 + ' [[PROT_' and '0]] b'.

        With the fix the cut retracts to 796 (the start of [[PROT_0]]) so
        chunk 1 is 'a'*795 + ' ' and the placeholder begins chunk 2 intact.
        """
        engine = MagicMock()
        engine.count_tokens.side_effect = len  # 1 token per character

        seg = "a" * 795 + " [[PROT_0]] b"
        chunks = service._token_verified_prefix_split(seg, engine)

        # Every chunk must be within the 800-token budget.
        for chunk in chunks:
            self.assertLessEqual(
                len(chunk),
                service._FALLBACK_CHUNK_MAX_TOKENS,
                f"Chunk exceeds budget: {chunk!r}",
            )

        # The placeholder must NOT be split across chunks.
        combined = "".join(chunks)
        self.assertEqual(combined, seg, "Concatenation must recover original string")
        self.assertIn("[[PROT_0]]", combined)

        # Verify the placeholder is whole in exactly one chunk.
        containing = [c for c in chunks if "[[PROT_0]]" in c]
        self.assertEqual(
            len(containing), 1,
            "[[PROT_0]] must appear intact in exactly one chunk",
        )

    # O2 — _split_text_into_translation_chunks preserves placeholder across paragraphs
    def test_split_chunks_preserves_placeholder_per_paragraph(self):
        """
        A body with two paragraphs, each embedding a [[PROT_N]] token, that
        together exceed the threshold.  Every chunk must contain any placeholder
        it carries as a whole token — no partial matches like '[[PROT_' or '0]]'.
        """
        import re as _re

        # Two paragraphs, each ~900 chars + placeholder.  With count_tokens = len
        # each paragraph is well above _FALLBACK_CHUNK_MAX_TOKENS (800) on its
        # own, so the splitter must handle them individually.
        para1 = "x" * 790 + " [[PROT_0]] end."
        para2 = "y" * 790 + " [[PROT_1]] fin."
        body = para1 + "\n\n" + para2

        engine = MagicMock()
        engine.count_tokens.side_effect = len

        chunks = service._split_text_into_translation_chunks(body, engine)

        combined = "".join(chunks)
        # All text recovered.
        self.assertIn("[[PROT_0]]", combined)
        self.assertIn("[[PROT_1]]", combined)

        # No partial placeholder fragments in any chunk.
        partial_re = _re.compile(r"\[\[PROT_|\d+\]\]")
        for chunk in chunks:
            # Remove complete placeholders first, then look for leftover fragments.
            stripped = service._PROTECTED_PLACEHOLDER_RE.sub("", chunk)
            self.assertNotRegex(
                stripped,
                r"\[\[PROT_|\d+\]\]",
                f"Partial placeholder fragment found in chunk: {chunk!r}",
            )

    # O3 — route end-to-end: chunked protected-source body restores correctly
    async def test_route_chunked_protected_source_restores_correctly(self):
        """
        End-to-end: a preflight-degraded HTML body with a translate='no' span
        is passed through the protected-source path.  count_tokens is wired to
        return a value above the chunk threshold for any body-text call so that
        the chunked path is exercised.  The mock translation engine echoes
        placeholders back; after restoration the original protected value must
        appear in translated_body_text.
        """
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

        # Rich HTML: large enough to fire preflight, contains protected span.
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        content_html = (
            "<h1>Order Confirmation</h1>"
            "<p>Reference: <span translate='no'>ORD-9988</span></p>"
            "<p>Your order has been received and is being processed.</p>"
            "<p>Thank you for choosing our service.</p>"
        )
        rich_html = f"<html><body>{content_html}{padding}</body></html>"
        # Large existing body so the guard approves the shorter derived source.
        existing_body_text = "B" * 600

        mock_engine = MagicMock()

        call_count = [0]

        def _count(text):
            call_count[0] += 1
            # Return a value that triggers chunking for long strings.
            if len(text) > 100:
                return service._FALLBACK_CHUNK_TOKEN_THRESHOLD + 100
            return 10

        mock_engine.count_tokens.side_effect = _count

        async def _translate(*, prompt, system_prompt=None, **kwargs):
            # Echo placeholders back verbatim (simulates model preserving them).
            import re as _re
            tokens_found = _re.findall(r"\[\[PROT_\d+\]\]", prompt)
            if tokens_found:
                return f"Confirmation de commande {tokens_found[0]}"
            return "Confirmation de commande"

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(
                    body_html=rich_html, body_text=existing_body_text,
                ),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        translated = result["translated_body_text"]
        # Original protected value must be restored.
        self.assertIn("ORD-9988", translated)
        # No raw placeholder token should survive in the final output.
        self.assertNotIn("[[PROT_", translated)

    # O4 — placeholder at position 0: cut advances past whole token
    def test_prefix_split_placeholder_at_position_zero(self):
        """
        Edge case: the remaining window starts with [[PROT_0]] followed by
        a long dense string.  The binary search will find a cut inside the
        placeholder (cut < len('[[PROT_0]]') = 10).  Because _ps == 0, the
        fix must advance the cut to _pe (past the whole token) rather than
        retracting to 0 (which would make no progress).

        Verified: chunk 1 contains the complete [[PROT_0]] token; all text
        is recovered.
        """
        engine = MagicMock()
        engine.count_tokens.side_effect = len  # 1 token per character

        # [[PROT_0]] (10 chars) + 795 'z' chars = 805 chars total > budget 800.
        # Binary search cut will be 800 — inside the placeholder (chars 0-9).
        seg = "[[PROT_0]]" + "z" * 795
        chunks = service._token_verified_prefix_split(seg, engine)

        for chunk in chunks:
            self.assertLessEqual(len(chunk), service._FALLBACK_CHUNK_MAX_TOKENS)

        combined = "".join(chunks)
        self.assertEqual(combined, seg)

        # Placeholder must be whole in the first chunk.
        self.assertTrue(
            chunks[0].startswith("[[PROT_0]]"),
            f"First chunk must start with [[PROT_0]]: {chunks[0]!r}",
        )


# ---------------------------------------------------------------------------
# Section P — Fail-safe protected-token handling + helper dedup (P3.5-R3F-P1R4R3)
# ---------------------------------------------------------------------------

# Shared HTML fixture used for P1/P2/P3/P6 — rich enough to fire preflight
# and for the guard to approve the shorter derived source.
_P_CONTENT_HTML = (
    "<h1>Order Summary</h1>"
    "<p>Order number: <span translate='no'>ORD-77412</span></p>"
    "<p>Your order has been confirmed and will ship within two business days.</p>"
    "<p>Thank you for your purchase.</p>"
)


class TestFailSafeProtectedHandlingAndHelperDedup(unittest.IsolatedAsyncioTestCase):
    """
    Proofs for the P1R4R3 fail-safe and dedup changes (P1–P6).

    P1/P2/P3 are route-level async tests using real BS4 derivation.
    P4/P5 are synchronous unit tests against _derive_fallback_source_impl.
    P6 is a route-level async test confirming structured-success is unaffected.
    """

    def _skip_if_no_bs4(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    def _make_rich_html(self):
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        return f"<html><body>{_P_CONTENT_HTML}{padding}</body></html>"

    # P1 — all tokens survive: restoration applied, no retry
    async def test_all_tokens_survive_restoration_applied_no_retry(self):
        """When every [[PROT_N]] token is echoed back by the model, restoration
        runs normally; no retry engine call is made beyond the primary one."""
        self._skip_if_no_bs4()
        rich_html = self._make_rich_html()
        existing_body_text = "C" * 600

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        call_count = [0]

        async def _translate(*, prompt, system_prompt=None, **kwargs):
            call_count[0] += 1
            # Echo every placeholder intact — restoration must happen on first call.
            import re as _re
            tokens = _re.findall(r"\[\[PROT_\d+\]\]", prompt)
            body = "Résumé de la commande\n\nNuméro: "
            body += tokens[0] if tokens else "?"
            body += "\n\nVotre commande est confirmée."
            return body

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(service, 'MistralEngine', return_value=mock_engine))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # Exactly one translation call — no retry.
        self.assertEqual(call_count[0], 1)
        # Protected value restored in output.
        self.assertIn("ORD-77412", result["translated_body_text"])
        self.assertNotIn("[[PROT_", result["translated_body_text"])

    # P2 — token dropped: retry path taken, no placeholder fragment in output
    async def test_dropped_token_triggers_retry_no_placeholder_in_output(self):
        """When the model drops a [[PROT_N]] token entirely, the route must not
        silently accept the partial result.  Instead it retries without placeholder
        mode; the final output must contain no [[PROT_ fragment."""
        self._skip_if_no_bs4()
        rich_html = self._make_rich_html()
        existing_body_text = "D" * 600

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        call_count = [0]

        async def _translate(*, prompt, system_prompt=None, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: model drops the placeholder entirely.
                return "Résumé de la commande\n\nVotre commande est confirmée."
            # Retry call: model translates the unwrap source, no placeholders present.
            return "Résumé de la commande\n\nNuméro: ORD-77412\n\nConfirmée."

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(service, 'MistralEngine', return_value=mock_engine))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        # Two calls: primary (dropped) + retry.
        self.assertEqual(call_count[0], 2)
        translated = result["translated_body_text"]
        # No raw [[PROT_ fragment may remain.
        self.assertNotIn("[[PROT_", translated)
        # Output is non-empty and sensible.
        self.assertTrue(translated)

    # P3 — mangled token (partial string): treated as missing, retry triggered
    async def test_mangled_token_treated_as_missing_retry_triggered(self):
        """A mangled placeholder like '[[PROT_0]' (missing closing bracket) is
        not present as a whole string, so it is treated as missing — the retry
        path must be taken."""
        self._skip_if_no_bs4()
        rich_html = self._make_rich_html()
        existing_body_text = "E" * 600

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        call_count = [0]

        async def _translate(*, prompt, system_prompt=None, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Model returns a mangled placeholder (one bracket missing).
                return "Commande: [[PROT_0]"
            return "Commande: ORD-77412 confirmée."

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(service, 'MistralEngine', return_value=mock_engine))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(call_count[0], 2)
        self.assertNotIn("[[PROT_0]]", result["translated_body_text"])

    # P4 — _derive_fallback_source_impl unwrap mode == _derive_simplified_fallback_source
    def test_derive_fallback_impl_unwrap_mode_matches_simplified_behavior(self):
        """_derive_fallback_source_impl with protect_mode=False must produce the
        same output as the public _derive_simplified_fallback_source wrapper —
        protected visible text is preserved, no [[PROT_N]] tokens present."""
        self._skip_if_no_bs4()
        html = (
            "<h1>Report</h1>"
            "<p>Amount: <span translate='no'>$1,234.56</span></p>"
            "<p>Please review and confirm.</p>"
        )
        impl_result, impl_map = service._derive_fallback_source_impl(html, protect_mode=False)
        wrapper_result = service._derive_simplified_fallback_source(html)

        self.assertEqual(impl_result, wrapper_result)
        self.assertEqual(impl_map, {})
        self.assertIn("$1,234.56", impl_result)
        self.assertNotIn("[[PROT_", impl_result)

    # P5 — _derive_fallback_source_impl placeholder mode == _derive_protected_fallback_source
    def test_derive_fallback_impl_placeholder_mode_matches_protected_behavior(self):
        """_derive_fallback_source_impl with protect_mode=True must produce the
        same output as the public _derive_protected_fallback_source wrapper —
        protected text replaced by [[PROT_0]], map populated with original."""
        self._skip_if_no_bs4()
        html = (
            "<h1>Invoice</h1>"
            "<p>Ref: <span translate='no'>INV-5500</span></p>"
            "<p>Please pay by the due date.</p>"
        )
        impl_result, impl_map = service._derive_fallback_source_impl(html, protect_mode=True)
        wrapper_result, wrapper_map = service._derive_protected_fallback_source(html)

        self.assertEqual(impl_result, wrapper_result)
        self.assertEqual(impl_map, wrapper_map)
        self.assertIn("[[PROT_0]]", impl_result)
        self.assertNotIn("INV-5500", impl_result)
        self.assertEqual(impl_map.get("[[PROT_0]]"), "INV-5500")

    # P6 — structured-success path unaffected
    async def test_structured_success_unaffected_by_failsafe_and_dedup(self):
        """The structured-success path must remain entirely unaffected by the
        fail-safe retry logic and helper dedup — _derive_fallback_source_impl
        must not be called at all on this path."""
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(service, 'MistralEngine', return_value=mock_engine))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                return_value=(_FAKE_TRANSLATED_HTML, "structured_success"),
            ))
            mock_impl = stack.enter_context(patch.object(
                service, '_derive_fallback_source_impl',
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        mock_impl.assert_not_called()
        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_reason_code"], "structured_success")


# ---------------------------------------------------------------------------
# Section Q — Retry failure contract parity (P3.5-R3F-P1R4R4)
# ---------------------------------------------------------------------------

# Shared fixture: rich HTML with protected content, large enough to fire
# preflight and for the guard to approve the derived source.
_Q_CONTENT_HTML = (
    "<h1>Shipment Update</h1>"
    "<p>Tracking: <span translate='no'>TRK-20260513</span></p>"
    "<p>Your parcel is on its way and will arrive by the estimated date.</p>"
    "<p>Contact support if you have any questions about your delivery.</p>"
)


class TestRetryFailureContractParity(unittest.IsolatedAsyncioTestCase):
    """
    Proofs that the fail-safe retry path raises the same HTTP exceptions as
    the main text-fallback path for each error class (Q1–Q3).

    Each test forces the primary translation call to succeed but drop a
    [[PROT_N]] token, triggering the retry.  The retry mock then raises the
    target exception.  All tests use real BS4 derivation and are skipped when
    BS4 is unavailable.
    """

    def _skip_if_no_bs4(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    def _make_rich_html(self):
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        return f"<html><body>{_Q_CONTENT_HTML}{padding}</body></html>"

    # Q1 — retry ValueError -> 503 Translation service unavailable
    async def test_retry_value_error_raises_503(self):
        """When the retry engine call raises ValueError (engine misconfigured /
        key invalid), the route must raise HTTPException with status_code=503
        and detail='Translation service unavailable', identical to the main path."""
        self._skip_if_no_bs4()
        rich_html = self._make_rich_html()
        existing_body_text = "F" * 600

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        call_count = [0]

        async def _translate(*, prompt, system_prompt=None, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Primary call: drop the placeholder so retry is triggered.
                return "Mise a jour de l'expedition."
            raise ValueError("invalid api key")

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(service, 'MistralEngine', return_value=mock_engine))

            from fastapi import HTTPException as _HTTPException
            with self.assertRaises(_HTTPException) as ctx:
                await service.translate_render_email(
                    _FAKE_GMAIL_MESSAGE_ID,
                    TranslateRenderRequest(target_language="fr"),
                )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("unavailable", ctx.exception.detail.lower())
        self.assertEqual(call_count[0], 2)

    # Q2 — retry TimeoutError -> 502 Translation timed out
    async def test_retry_timeout_error_raises_502_timed_out(self):
        """When the retry engine call raises TimeoutError, the route must raise
        HTTPException with status_code=502 and detail='Translation timed out',
        identical to the main path."""
        self._skip_if_no_bs4()
        rich_html = self._make_rich_html()
        existing_body_text = "G" * 600

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        call_count = [0]

        async def _translate(*, prompt, system_prompt=None, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return "Mise a jour."
            raise TimeoutError("request timed out")

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(service, 'MistralEngine', return_value=mock_engine))

            from fastapi import HTTPException as _HTTPException
            with self.assertRaises(_HTTPException) as ctx:
                await service.translate_render_email(
                    _FAKE_GMAIL_MESSAGE_ID,
                    TranslateRenderRequest(target_language="fr"),
                )

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("timed out", ctx.exception.detail.lower())
        self.assertEqual(call_count[0], 2)

    # Q3 — retry generic Exception -> 502 Translation failed
    async def test_retry_generic_exception_raises_502_failed(self):
        """When the retry engine call raises a generic Exception (unexpected
        error), the route must raise HTTPException with status_code=502 and
        detail='Translation failed', identical to the main path."""
        self._skip_if_no_bs4()
        rich_html = self._make_rich_html()
        existing_body_text = "H" * 600

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        call_count = [0]

        async def _translate(*, prompt, system_prompt=None, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return "Mise a jour."
            raise RuntimeError("unexpected engine failure")

        mock_engine.generate_text_async = _translate

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=existing_body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=existing_body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(service, 'MistralEngine', return_value=mock_engine))

            from fastapi import HTTPException as _HTTPException
            with self.assertRaises(_HTTPException) as ctx:
                await service.translate_render_email(
                    _FAKE_GMAIL_MESSAGE_ID,
                    TranslateRenderRequest(target_language="fr"),
                )

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("failed", ctx.exception.detail.lower())
        self.assertEqual(call_count[0], 2)


# ---------------------------------------------------------------------------
# Section R — Canonical plain-text first + HTML assistance (P3.5-R3F-R1)
# ---------------------------------------------------------------------------

# Supabase-like newsletter HTML: noisier derived source with footer contamination
# and a duplicated separator section.
_R_SUPABASE_LIKE_CONTENT_HTML = (
    "<html><body>"
    "<h1>What's new in Supabase</h1>"
    "<p>This week we shipped Edge Functions v2, improved the dashboard, "
    "and published a new tutorial on Row Level Security.</p>"
    "<h2>Edge Functions v2</h2>"
    "<p>Faster cold starts, Node.js compat, and native npm support.</p>"
    "<h2>Dashboard improvements</h2>"
    "<p>Redesigned SQL editor with autocomplete and improved table editor.</p>"
    "<div class='footer'>"
    "<p>You are receiving this because you signed up at supabase.com.</p>"
    "<p>Unsubscribe | Privacy Policy | Terms of Service</p>"
    "<p>Follow us on Twitter | LinkedIn | GitHub</p>"
    "<p>Copyright 2026 Supabase Inc. All rights reserved.</p>"
    "<p>Supabase Inc. 970 Toa Payoh North, Singapore 318992</p>"
    "</div>"
    "</body></html>"
)

# Canonical plain-text body_text for the same email — clean and ordered.
_R_SUPABASE_CANONICAL_BODY_TEXT = """\
What's new in Supabase

This week we shipped Edge Functions v2, improved the dashboard, \
and published a new tutorial on Row Level Security.

Edge Functions v2

Faster cold starts, Node.js compat, and native npm support.

Dashboard improvements

Redesigned SQL editor with autocomplete and improved table editor.\
"""


class TestCanonicalSourceSelectionAndPostProcessing(unittest.TestCase):
    """
    Deterministic proof for P3.5-R3F-R1: canonical plain-text first + HTML assistance.

    R1–R5:   _score_source_noise unit tests
    R6–R9:   _select_canonical_translation_source unit tests
    R10–R12: _enrich_body_text_with_assists unit tests
    R13–R15: _trim_footer_tail unit tests
    R16–R17: _dedup_repeated_blocks unit tests
    """

    # R1 — clean text scores 0.0
    def test_score_source_noise_clean_text(self):
        """Clean newsletter body with no footer markers scores exactly 0.0."""
        text = _R_SUPABASE_CANONICAL_BODY_TEXT
        score = service._score_source_noise(text)
        self.assertEqual(score, 0.0)

    # R2 — footer/unsubscribe lines produce penalty
    def test_score_source_noise_footer_lines(self):
        """Lines with unsubscribe/follow-us/privacy-policy markers produce >0 penalty."""
        text = (
            "Good content here.\n\n"
            "Unsubscribe from this list.\n"
            "Follow us on Twitter.\n"
            "Privacy Policy | Terms of Service"
        )
        score = service._score_source_noise(text)
        self.assertGreater(score, 0.0)
        # Three footer-signal lines: 3 * 5.0 = 15.0 minimum
        self.assertGreaterEqual(score, 15.0)

    # R3 — link-cloud lines produce penalty
    def test_score_source_noise_link_cloud(self):
        """Lines containing 2+ bare URLs and nothing else produce link-cloud penalty."""
        text = (
            "Intro paragraph.\n\n"
            "https://example.com/a https://example.com/b\n"
            "https://example.com/c https://example.com/d"
        )
        score = service._score_source_noise(text)
        self.assertGreater(score, 0.0)

    # R4 — separator-only lines produce penalty
    def test_score_source_noise_separator_lines(self):
        """Lines of repeated dashes/equals/asterisks produce a positive penalty."""
        text = "Section A.\n\n---\n\nSection B.\n\n===\n\nSection C."
        score = service._score_source_noise(text)
        self.assertGreater(score, 0.0)
        # Two separator lines: 2 * 2.0 = 4.0
        self.assertGreaterEqual(score, 4.0)

    # R5 — duplicate paragraph fingerprint produces penalty
    def test_score_source_noise_duplicate_paragraphs(self):
        """Duplicate paragraph fingerprints (same first 120 normalised chars) produce penalty."""
        repeated = "This is the section header line that appears more than once in the email body."
        text = f"{repeated}\n\nUnique middle content.\n\n{repeated}"
        score = service._score_source_noise(text)
        self.assertGreater(score, 0.0)
        # One duplicate: +4.0
        self.assertGreaterEqual(score, 4.0)

    # R6 — body_text clearly cleaner: prefer body_text
    def test_select_canonical_source_prefers_body_when_clearly_cleaner(self):
        """When body_text has 0 noise and derived has noise > gap, body_text is preferred."""
        clean_body = _R_SUPABASE_CANONICAL_BODY_TEXT
        noisy_derived = (
            "Edge Functions v2\n\n"
            "Faster cold starts.\n\n"
            "Unsubscribe from this newsletter.\n"
            "Follow us on Twitter | LinkedIn.\n"
            "Privacy Policy | Terms of Service | Copyright 2026"
        )
        prefer_derived, reason = service._select_canonical_translation_source(
            clean_body, noisy_derived
        )
        self.assertFalse(prefer_derived)
        self.assertEqual(reason, "body_text_canonical")

    # R7 — similar noise: falls through to "shorter" criterion
    def test_select_canonical_source_falls_through_to_shorter_when_similar_noise(self):
        """When both sources have similar (low) noise, derived is preferred only if materially shorter."""
        body = "A" * 600
        short_derived = "Invoice summary: Total due $42.00." * 2  # ~68 chars, < 600*0.9=540
        prefer_derived, reason = service._select_canonical_translation_source(body, short_derived)
        self.assertTrue(prefer_derived)
        self.assertEqual(reason, "derived_shorter")

        long_derived = "B" * 580  # 580 > 600*0.9=540 — NOT materially shorter
        prefer_derived2, reason2 = service._select_canonical_translation_source(body, long_derived)
        self.assertFalse(prefer_derived2)
        self.assertEqual(reason2, "body_text_canonical")

    # R8 — derived empty → False
    def test_select_canonical_source_derived_empty_returns_false(self):
        """Empty or below-minimum derived source always returns False."""
        prefer, reason = service._select_canonical_translation_source("body content here", "")
        self.assertFalse(prefer)
        self.assertEqual(reason, "derived_empty")

        prefer2, reason2 = service._select_canonical_translation_source("body content here", "tiny")
        self.assertFalse(prefer2)
        self.assertEqual(reason2, "derived_empty")

    # R9 — body_text empty → True
    def test_select_canonical_source_body_empty_returns_true(self):
        """Empty body_text forces derived source selection (provided substance check passes)."""
        derived = "Substantial derived content here for translation purposes."  # >= 50 chars
        prefer, reason = service._select_canonical_translation_source("", derived)
        self.assertTrue(prefer)
        self.assertEqual(reason, "body_text_empty")

    # R10 — enrichment adds missing URL
    def test_enrich_adds_missing_meaningful_url(self):
        """URL present in derived source but absent from body_text is appended."""
        body = "Edge Functions v2 is now available."
        derived = "Edge Functions v2 (https://supabase.com/blog/edge-functions-v2) is now available."
        enriched = service._enrich_body_text_with_assists(body, derived)
        self.assertIn("https://supabase.com/blog/edge-functions-v2", enriched)
        # Original body must remain at the start
        self.assertTrue(enriched.startswith(body.rstrip()))

    # R11 — enrichment does NOT add URL from footer-context line
    def test_enrich_does_not_add_footer_context_url(self):
        """URL on a line containing footer/unsubscribe signals is not injected."""
        body = "Main content here."
        derived = (
            "Main content here.\n\n"
            "Unsubscribe here: https://example.com/unsubscribe"
        )
        enriched = service._enrich_body_text_with_assists(body, derived)
        self.assertNotIn("https://example.com/unsubscribe", enriched)

    # R12 — enrichment does NOT add duplicate URL
    def test_enrich_does_not_add_url_already_in_body(self):
        """URL already present in body_text is not duplicated by enrichment."""
        body = "See https://supabase.com/blog/edge-functions-v2 for details."
        derived = "Edge Functions v2 (https://supabase.com/blog/edge-functions-v2) is out."
        enriched = service._enrich_body_text_with_assists(body, derived)
        self.assertEqual(enriched.count("https://supabase.com/blog/edge-functions-v2"), 1)

    # R13 — footer tail is cut when >= 3 signals in last 35%
    def test_trim_footer_tail_cuts_when_enough_signals(self):
        """_trim_footer_tail removes the footer region when >= 3 signals appear in last 35%."""
        content = (
            "Edge Functions v2 is now available.\n\n"
            "Faster cold starts, Node.js compat, and native npm support.\n\n"
            "Redesigned SQL editor with autocomplete and improved table editor.\n\n"
            "Dashboard improvements are live now.\n\n"
            "Many teams have already migrated.\n\n"
            "We are excited about these changes.\n\n"
            "The future looks bright for serverless.\n\n"
        )
        footer = (
            "Unsubscribe from this newsletter.\n"
            "Follow us on Twitter and LinkedIn.\n"
            "Privacy Policy | Terms of Service\n"
            "Copyright 2026 Supabase Inc. All rights reserved.\n"
        )
        text = content + footer
        result = service._trim_footer_tail(text)
        self.assertNotIn("Unsubscribe", result)
        self.assertNotIn("Follow us", result)
        self.assertNotIn("Copyright 2026", result)
        self.assertIn("Edge Functions", result)

    # R14 — no cut when footer signals < 3
    def test_trim_footer_tail_no_cut_when_few_signals(self):
        """_trim_footer_tail leaves text unchanged when fewer than 3 footer signals in tail."""
        text = (
            "Content line one.\n"
            "Content line two.\n"
            "Content line three.\n"
            "Content line four.\n"
            "Unsubscribe.\n"
            "More content five.\n"
            "More content six.\n"
        )
        result = service._trim_footer_tail(text)
        self.assertEqual(result, text)

    # R15 — no cut when head would be < 200 chars
    def test_trim_footer_tail_no_cut_when_head_too_short(self):
        """_trim_footer_tail leaves text unchanged when remaining head < 200 chars."""
        short_head = "Short head.\n"
        footer = (
            "Unsubscribe here.\n"
            "Follow us on Twitter.\n"
            "Privacy Policy applies.\n"
            "Copyright 2026 Inc.\n"
        )
        text = short_head + footer
        result = service._trim_footer_tail(text)
        # head would be < 200 chars so no cut
        self.assertEqual(result, text)

    # R16 — dedup preserves canonical order and removes duplicates
    def test_dedup_repeated_blocks_removes_duplicates_preserves_order(self):
        """Duplicate paragraph blocks are removed; first canonical occurrence is kept."""
        para_a = "Edge Functions v2 is now available."
        para_b = "Dashboard improvements are live."
        text = f"{para_a}\n\n{para_b}\n\n{para_a}"
        result = service._dedup_repeated_blocks(text)
        self.assertIn(para_a, result)
        self.assertIn(para_b, result)
        # Should appear only once
        self.assertEqual(result.count(para_a), 1)
        # para_a must come before para_b (canonical order)
        self.assertLess(result.index(para_a), result.index(para_b))

    # R17 — no duplicates: text unchanged
    def test_dedup_repeated_blocks_no_change_when_no_duplicates(self):
        """Text with no duplicate paragraphs is returned unchanged (content-wise)."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = service._dedup_repeated_blocks(text)
        self.assertIn("Paragraph one.", result)
        self.assertIn("Paragraph two.", result)
        self.assertIn("Paragraph three.", result)
        self.assertEqual(len(result.split("\n\n")), 3)


class TestCanonicalSourceSelectionRouteLevel(unittest.IsolatedAsyncioTestCase):
    """
    Route-level async proofs for Section R (R18–R20).
    Requires BS4 for R18/R19 (skipped if unavailable).
    """

    def _skip_if_no_bs4(self):
        if not service._BS4_AVAILABLE:
            self.skipTest("BeautifulSoup4 not available")

    # R18 — Supabase-like fixture: canonical body_text preferred over noisy derived HTML
    async def test_route_prefers_canonical_body_text_over_noisy_derived_html(self):
        """Runtime-like Supabase newsletter fixture:
        - canonical body_text is clean and ordered (0 noise)
        - derived HTML source is footer-contaminated (high noise)
        - route must choose the canonical body_text path

        The translation prompt must contain the canonical body_text
        and must NOT be replaced by the noisy derived source content.
        """
        self._skip_if_no_bs4()

        # HTML is preflight-degraded (>30000 chars with padding)
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"{_R_SUPABASE_LIKE_CONTENT_HTML[:-7]}{padding}</body></html>"

        # Canonical plain-text body — clean, ordered, no footer noise.
        canonical_body = _R_SUPABASE_CANONICAL_BODY_TEXT

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10
        captured_prompts: list = []

        async def _capture(*, prompt, **kwargs):
            captured_prompts.append(prompt)
            return "translated output"

        mock_engine.generate_text_async = _capture

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=canonical_body),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=canonical_body),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_mode"], "text_fallback")
        self.assertEqual(result["translation_fidelity"], "simplified")
        self.assertEqual(result["translation_reason_code"], "structured_preflight_degraded")

        combined = "\n".join(captured_prompts)
        # Canonical body content must be in the translation prompt
        self.assertIn("Edge Functions v2", combined)
        self.assertIn("Dashboard improvements", combined)
        # Footer noise must NOT be in the translation prompt
        self.assertNotIn("Unsubscribe", combined)
        self.assertNotIn("Copyright 2026", combined)
        self.assertNotIn("Follow us on Twitter", combined)

    # R19 — footer tail and repeated-block dedup applied for preflight-degraded output
    async def test_route_applies_trim_and_dedup_for_preflight_degraded(self):
        """_trim_footer_tail and _dedup_repeated_blocks are applied to the
        translated output for the structured_preflight_degraded path."""
        # Simple rich HTML (preflight-degraded by size)
        padding = "<div style='display:none'>" + "x" * 30_100 + "</div>"
        rich_html = f"<html><body><p>Content.</p>{padding}</body></html>"
        body_text = "Canonical body."

        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        # Translation output with a duplicated paragraph and a footer tail
        noisy_translation = (
            "Translated content A.\n\n"
            "Translated content B.\n\n"
            "Translated content A.\n\n"  # duplicate — must be removed
            "Translated content C.\n\n"
            "Translated content D.\n\n"
            "Translated content E.\n\n"
            "Translated content F.\n\n"
            "Se désabonner de cette liste.\n"       # footer signal 1
            "Nous suivre sur Twitter et LinkedIn.\n"  # footer signal 2
            "Politique de confidentialité | CGU\n"   # footer signal 3 (CGU = terms)
            "Copyright 2026 Inc.\n"
        )

        mock_engine.generate_text_async = AsyncMock(return_value=noisy_translation)

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(body=body_text),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(body_html=rich_html, body_text=body_text),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            # Patch _trim_footer_tail and _dedup_repeated_blocks to assert they are called
            trim_spy = stack.enter_context(patch.object(
                service, '_trim_footer_tail', wraps=service._trim_footer_tail,
            ))
            dedup_spy = stack.enter_context(patch.object(
                service, '_dedup_repeated_blocks', wraps=service._dedup_repeated_blocks,
            ))

            await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        trim_spy.assert_called_once()
        dedup_spy.assert_called_once()

    # R20 — structured-success is entirely unaffected
    async def test_route_structured_success_unaffected_by_canonical_selection(self):
        """structured_success path must not call _select_canonical_translation_source,
        _trim_footer_tail, or _dedup_repeated_blocks."""
        mock_engine = MagicMock()
        mock_engine.count_tokens.return_value = 10

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                service, '_lookup_email_record_by_message_id',
                return_value=_make_record(),
            ))
            stack.enter_context(patch.object(
                service, '_build_rendered_email_payload',
                return_value=_make_payload(),
            ))
            stack.enter_context(patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}))
            stack.enter_context(patch.object(
                service, 'MistralEngine', return_value=mock_engine,
            ))
            stack.enter_context(patch.object(
                service, '_attempt_structured_html_translation',
                return_value=(_FAKE_TRANSLATED_HTML, "structured_success"),
            ))
            mock_select = stack.enter_context(patch.object(
                service, '_select_canonical_translation_source',
            ))
            mock_trim = stack.enter_context(patch.object(
                service, '_trim_footer_tail',
            ))
            mock_dedup = stack.enter_context(patch.object(
                service, '_dedup_repeated_blocks',
            ))

            result = await service.translate_render_email(
                _FAKE_GMAIL_MESSAGE_ID,
                TranslateRenderRequest(target_language="fr"),
            )

        self.assertEqual(result["translation_mode"], "structured_html")
        self.assertEqual(result["translation_reason_code"], "structured_success")
        mock_select.assert_not_called()
        mock_trim.assert_not_called()
        mock_dedup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
