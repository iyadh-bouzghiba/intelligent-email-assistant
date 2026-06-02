"""Deterministic prompt builder for EBAQ email summaries.

Combines a fixed category code with a DIM2 language code to produce
a structured prompt string. No AI, no network, no external dependencies.
"""

__all__ = [
    "LATIN_LANGUAGES",
    "SEMITIC_LANGUAGES",
    "EAST_ASIAN_LANGUAGES",
    "resolve_language_family",
    "build_summary_prompt",
]

LATIN_LANGUAGES: tuple[str, ...] = ("en", "de", "fr", "es", "pt-BR", "tr")
SEMITIC_LANGUAGES: tuple[str, ...] = ("ar",)
EAST_ASIAN_LANGUAGES: tuple[str, ...] = ("zh", "ja", "ko")

# Exact language names used in the output-language enforcement instruction
_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "fr": "French",
    "ar": "Arabic",
    "de": "German",
    "es": "Spanish",
    "pt-BR": "Brazilian Portuguese",
    "tr": "Turkish",
    "zh": "Simplified Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

_VALID_CATEGORIES: tuple[str, ...] = (
    "SECURITY_ACCOUNT",
    "FINANCIAL_LEGAL",
    "ACTION_REQUIRED",
    "SCHEDULING",
    "PROJECT_WORK",
    "AUTOMATED_SYSTEM",
    "CONTENT_INFO",
    "PERSONAL_SOCIAL",
    "CONVERSATION",
    "UNCATEGORIZED",
)

_CATEGORY_HINTS: dict[str, str] = {
    "SECURITY_ACCOUNT": (
        "Focus on account risk, the security event, "
        "access implications, and the immediate next action."
    ),
    "FINANCIAL_LEGAL": (
        "Focus on money, contract, or compliance facts. "
        "Highlight key amounts, dates, and obligations."
    ),
    "ACTION_REQUIRED": (
        "Focus on the specific action the recipient must take "
        "and the deadline."
    ),
    "SCHEDULING": (
        "Focus on meeting details: time, location, "
        "availability changes, or confirmation needed."
    ),
    "PROJECT_WORK": (
        "Focus on workstream or project status, blockers, "
        "deliverables, and the next work step."
    ),
    "AUTOMATED_SYSTEM": (
        "Focus on the system or tool event, its operational impact, "
        "and any required follow-up."
    ),
    "CONTENT_INFO": (
        "Summarise the high-level topic. "
        "Do not expand article by article."
    ),
    "PERSONAL_SOCIAL": (
        "Focus on the social or personal purpose "
        "and any expected response."
    ),
    "CONVERSATION": (
        "Focus on the conversational context "
        "and what reply is expected next."
    ),
    "UNCATEGORIZED": (
        "Keep the summary neutral and concise."
    ),
}

_FAMILY_INSTRUCTIONS: dict[str, str] = {
    "LATIN": (
        "Use a direct linear structure. "
        "Keep the overview to 2-3 sentences. "
        "When action items exist, present them as numbered items "
        "with deadlines when available."
    ),
    "SEMITIC": (
        "Use formal Modern Standard Arabic. "
        "Integrate action items into concise prose "
        "rather than bullet fragments."
    ),
    "EAST_ASIAN": (
        "Structure the overview as: "
        "topic first, then context, then action."
    ),
}


def resolve_language_family(language_code: str) -> str:
    """Return the language family for *language_code*.

    Defaults to LATIN for unknown or empty codes.
    """
    if language_code in SEMITIC_LANGUAGES:
        return "SEMITIC"
    if language_code in EAST_ASIAN_LANGUAGES:
        return "EAST_ASIAN"
    return "LATIN"


def _normalise_category(category_code: str) -> str:
    """Return a valid category code, defaulting to UNCATEGORIZED."""
    code = (category_code or "").strip().upper()
    if code in _VALID_CATEGORIES:
        return code
    return "UNCATEGORIZED"


def _normalise_language(dim2_language_code: str) -> str:
    """Return a supported language code, defaulting to en."""
    lang = (dim2_language_code or "").strip()
    all_langs = LATIN_LANGUAGES + SEMITIC_LANGUAGES + EAST_ASIAN_LANGUAGES
    if lang in all_langs:
        return lang
    return "en"


def build_summary_prompt(
    category_code: str,
    dim2_language_code: str,
) -> str:
    """Build a deterministic summary prompt for a category and language.

    Instructs the model to return only a JSON object with overview,
    action_items, and urgency. Category is fixed; model must not change it.
    """
    category = _normalise_category(category_code)
    language = _normalise_language(dim2_language_code)
    family = resolve_language_family(language)

    language_name = _LANGUAGE_NAMES.get(language, _LANGUAGE_NAMES["en"])
    category_hint = _CATEGORY_HINTS[category]
    family_instruction = _FAMILY_INSTRUCTIONS[family]

    if language == "en":
        lang_enforcement = (
            "Write overview and action_items strictly in English."
        )
    else:
        lang_enforcement = (
            f"Write overview and action_items strictly in {language_name}. "
            "Do not use English unless the target language is English."
        )

    prompt = (
        "You are an email summarisation assistant.\n\n"
        "The category is already decided. "
        "Do not choose, infer, rename, or change it.\n"
        f"Pre-classified category: {category}.\n\n"
        f"Category guidance: {category_hint}\n\n"
        f"Language and structure: {family_instruction}\n\n"
        f"Output language: {lang_enforcement}\n\n"
        "Return ONLY valid JSON. No prose outside the JSON object.\n"
        "The JSON must contain exactly these three fields:\n"
        '  "overview"     - string\n'
        '  "action_items" - list of strings (empty list if none)\n'
        '  "urgency"      - one of: low, medium, high\n\n'
        "Do not output category in your response.\n"
        "Do not add any explanation, markdown, or text outside the JSON."
    )
    return prompt
