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
    "de": {
        "label": "German",
        "native": "Deutsch",
        "summary_instruction": (
            "Schreibe alle für den Benutzer sichtbaren Textfelder auf Deutsch. "
            "Behalte das JSON-Schema unverändert bei. "
            'Das Feld "urgency" muss genau einen der Werte "low", "medium" oder "high" enthalten. '
            'Das Feld "category" muss genau einen der Werte '
            '"action_required", "informational", "meeting", "finance", "travel" oder "alert" enthalten.'
        ),
        "draft_instruction": (
            "Verfasse die Antwort ausschließlich auf Deutsch. "
            "Gib nur den Antworttext zurück, ohne Präambel, Erklärung oder Betreffzeile."
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
    "es": {
        "label": "Spanish",
        "native": "Español",
        "summary_instruction": (
            "Escribe todos los campos de texto visibles para el usuario en español. "
            "Mantén el esquema JSON sin cambios. "
            'El campo "urgency" debe ser exactamente uno de "low", "medium" o "high". '
            'El campo "category" debe ser exactamente uno de '
            '"action_required", "informational", "meeting", "finance", "travel" o "alert".'
        ),
        "draft_instruction": (
            "Redacta el borrador de respuesta únicamente en español. "
            "Devuelve solo el cuerpo de la respuesta, sin preámbulo, explicación ni línea de asunto."
        ),
    },
    "pt-BR": {
        "label": "Portuguese (Brazil)",
        "native": "Português (Brasil)",
        "summary_instruction": (
            "Escreva todos os campos de texto visíveis ao usuário em português do Brasil. "
            "Mantenha o esquema JSON inalterado. "
            'O campo "urgency" deve ser exatamente um de "low", "medium" ou "high". '
            'O campo "category" deve ser exatamente um de '
            '"action_required", "informational", "meeting", "finance", "travel" ou "alert".'
        ),
        "draft_instruction": (
            "Escreva o rascunho da resposta somente em português do Brasil. "
            "Retorne apenas o corpo da resposta, sem preâmbulo, explicação ou linha de assunto."
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
    "zh": {
        "label": "Chinese (Simplified)",
        "native": "简体中文",
        "summary_instruction": (
            "用简体中文书写所有用户可见的自然语言字段。"
            "保持 JSON 架构不变。"
            '"urgency" 字段必须严格为 "low"、"medium" 或 "high" 之一。'
            '"category" 字段必须严格为 '
            '"action_required"、"informational"、"meeting"、"finance"、"travel" 或 "alert" 之一。'
        ),
        "draft_instruction": (
            "仅用简体中文撰写回复草稿。"
            "只返回回复正文，不含前言、说明或主题行。"
        ),
    },
    "ja": {
        "label": "Japanese",
        "native": "日本語",
        "summary_instruction": (
            "ユーザーに表示されるすべての自然言語フィールドを日本語で記述してください。"
            "JSONスキーマは変更せずそのまま維持してください。"
            '"urgency"フィールドは "low"、"medium"、"high" のいずれかでなければなりません。'
            '"category"フィールドは "action_required"、"informational"、"meeting"、'
            '"finance"、"travel"、"alert" のいずれかでなければなりません。'
        ),
        "draft_instruction": (
            "返信の下書きを日本語のみで作成してください。"
            "前文、説明、件名行を含めず、返信本文のみを返してください。"
        ),
    },
    "ko": {
        "label": "Korean",
        "native": "한국어",
        "summary_instruction": (
            "사용자에게 표시되는 모든 자연어 필드를 한국어로 작성하십시오. "
            "JSON 스키마는 변경하지 않고 그대로 유지하십시오. "
            '"urgency" 필드는 "low", "medium", "high" 중 하나여야 합니다. '
            '"category" 필드는 "action_required", "informational", "meeting", '
            '"finance", "travel", "alert" 중 하나여야 합니다.'
        ),
        "draft_instruction": (
            "답장 초안을 한국어로만 작성하십시오. "
            "서문, 설명, 제목 줄 없이 답장 본문만 반환하십시오."
        ),
    },
}

DEFAULT_LANGUAGE = "en"

# DIM3 translation-language contract — independent from DIM2 SUPPORTED_LANGUAGES.
# Expand this set separately when new translation targets are enabled.
TRANSLATION_LANGUAGES: frozenset = frozenset({"en", "fr", "ar"})
DEFAULT_TRANSLATION_LANGUAGE = "en"

TRANSLATION_LANGUAGE_LABELS: dict = {
    "en": "English",
    "fr": "French",
    "ar": "Arabic",
}


def normalize_language(value) -> str:
    """Normalize any value to a supported language code, defaulting to English.

    Performs exact-match first, then case-insensitive fallback so that BCP47
    codes like 'pt-BR' are matched regardless of how the caller cased them.
    """
    stripped = (value or DEFAULT_LANGUAGE).strip()
    if stripped in SUPPORTED_LANGUAGES:
        return stripped
    lower = stripped.lower()
    for code in SUPPORTED_LANGUAGES:
        if code.lower() == lower:
            return code
    return DEFAULT_LANGUAGE


def normalize_translation_language(value) -> str:
    """Normalize any value to a supported DIM3 translation language code, defaulting to English."""
    normalized = (value or DEFAULT_TRANSLATION_LANGUAGE).strip().lower()
    if normalized in TRANSLATION_LANGUAGES:
        return normalized
    return DEFAULT_TRANSLATION_LANGUAGE


def get_translation_label(language: str) -> str:
    """Return the display label for a DIM3 translation language code."""
    return TRANSLATION_LANGUAGE_LABELS.get(
        normalize_translation_language(language), "English"
    )


def get_summary_instruction(language: str) -> str:
    """Return the summarization prompt instruction for the given language."""
    return SUPPORTED_LANGUAGES[normalize_language(language)]["summary_instruction"]


def get_draft_instruction(language: str) -> str:
    """Return the draft-reply prompt instruction for the given language."""
    return SUPPORTED_LANGUAGES[normalize_language(language)]["draft_instruction"]
