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


if __name__ == "__main__":
    unittest.main()
