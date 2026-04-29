"""
Central language registry for AI output language preferences.

Single source of truth for supported language codes, UI labels, and
prompt instructions consumed by the summarizer worker, agent, API
validator, and the frontend /api/preferences/languages endpoint.

Adding a new language requires only:
  1. A new entry in SUPPORTED_LANGUAGES
  2. A corresponding update to the DB CHECK constraint in setup_schema.sql
"""

SUPPORTED_LANGUAGES: dict = {
    "en": {
        "label": "English",
        "native": "English",
        "summary_instruction": (
            "Write all user-visible natural-language fields in English. "
            "Keep the JSON schema unchanged. "
            'The "urgency" field must remain exactly one of "low", "medium", or "high". '
            'The "category" field must remain exactly one of '
            '"action_required", "informational", "meeting", "finance", "travel", or "alert".'
        ),
        "draft_instruction": (
            "Write the draft reply in English only. "
            "Return only the reply body text, with no preamble, no explanation, and no subject line."
        ),
    },
    "fr": {
        "label": "French",
        "native": "Français",
        "summary_instruction": (
            "Écris tous les champs visibles par l'utilisateur en français. "
            "Conserve strictement le schéma JSON inchangé. "
            'Le champ "urgency" doit rester exactement une des valeurs "low", "medium" ou "high". '
            'Le champ "category" doit rester exactement une des valeurs '
            '"action_required", "informational", "meeting", "finance", "travel" ou "alert".'
        ),
        "draft_instruction": (
            "Rédige la réponse en français uniquement. "
            "Retourne uniquement le corps de la réponse, sans préambule, sans explication et sans objet."
        ),
    },
    "ar": {
        "label": "Arabic",
        "native": "العربية",
        "summary_instruction": (
            "اكتب جميع الحقول النصية الظاهرة للمستخدم باللغة العربية. "
            "يجب الإبقاء على مخطط JSON كما هو دون أي تغيير. "
            'يجب أن تبقى قيمة الحقل "urgency" واحدة فقط من "low" أو "medium" أو "high". '
            'ويجب أن تبقى قيمة الحقل "category" واحدة فقط من '
            '"action_required" أو "informational" أو "meeting" أو "finance" أو "travel" أو "alert".'
        ),
        "draft_instruction": (
            "اكتب مسودة الرد باللغة العربية فقط. "
            "أعد نص الرد فقط دون أي تمهيد أو شرح أو سطر موضوع."
        ),
    },
}

DEFAULT_LANGUAGE = "en"


def normalize_language(value) -> str:
    """Normalize any value to a supported language code, defaulting to English."""
    normalized = (value or DEFAULT_LANGUAGE).strip().lower()
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE


def get_summary_instruction(language: str) -> str:
    """Return the summarization prompt instruction for the given language."""
    return SUPPORTED_LANGUAGES[normalize_language(language)]["summary_instruction"]


def get_draft_instruction(language: str) -> str:
    """Return the draft-reply prompt instruction for the given language."""
    return SUPPORTED_LANGUAGES[normalize_language(language)]["draft_instruction"]
