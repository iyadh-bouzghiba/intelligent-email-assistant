"""Shared helpers for resolving AI summary language variants."""

from typing import Any, Dict, List, Optional


def resolve_summary_for_language(
    rows: List[Dict[str, Any]],
    preferred_language: str,
) -> Optional[Dict[str, Any]]:
    """
    Resolve a summary row from caller-ordered language variants.

    Caller ordering is preserved. Callers should pass rows newest-first when
    newest duplicate language variants should win.

    Resolution policy:
    1. preferred_language
    2. English fallback
    3. first available row
    4. None for empty input
    """
    if not rows:
        return None

    by_lang: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        lang = row.get("summary_language", "en")
        if lang not in by_lang:
            by_lang[lang] = row

    return by_lang.get(preferred_language) or by_lang.get("en") or rows[0]
