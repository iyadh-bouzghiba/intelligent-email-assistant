from backend.utils.summary_utils import resolve_summary_for_language


def test_returns_preferred_language_row():
    fr_row = {"summary_language": "fr", "summary_text": "French summary"}
    en_row = {"summary_language": "en", "summary_text": "Summary"}
    result = resolve_summary_for_language([fr_row, en_row], "fr")
    assert result is fr_row


def test_falls_back_to_english_when_preferred_missing():
    en_row = {"summary_language": "en", "summary_text": "Summary"}
    de_row = {"summary_language": "de", "summary_text": "Zusammenfassung"}
    result = resolve_summary_for_language([en_row, de_row], "fr")
    assert result is en_row


def test_falls_back_to_first_available_row():
    de_row = {"summary_language": "de", "summary_text": "Zusammenfassung"}
    ja_row = {"summary_language": "ja", "summary_text": "Japanese summary"}
    result = resolve_summary_for_language([de_row, ja_row], "fr")
    assert result is de_row


def test_returns_none_for_empty_rows():
    assert resolve_summary_for_language([], "en") is None
    assert resolve_summary_for_language([], "fr") is None


def test_preserves_caller_order_for_duplicate_languages():
    first_en = {"summary_language": "en", "summary_text": "First"}
    second_en = {"summary_language": "en", "summary_text": "Second"}
    result = resolve_summary_for_language([first_en, second_en], "en")
    assert result is first_en


def test_missing_summary_language_behaves_as_english():
    row_no_lang = {"summary_text": "No lang key"}
    result = resolve_summary_for_language([row_no_lang], "en")
    assert result is row_no_lang
