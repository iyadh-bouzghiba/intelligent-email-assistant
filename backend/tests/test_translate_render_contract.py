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


if __name__ == "__main__":
    unittest.main()
