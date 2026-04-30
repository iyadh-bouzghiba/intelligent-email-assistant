"""
Tone registry for AI draft reply generation.

Design contract:
- This file is the single source of truth for supported draft tones.
- New tones should be added here only.
- Callers must use normalize_tone() before reading registry values.
"""

from typing import Optional

SUPPORTED_TONES: dict = {
    "professional": {
        "label": "Professional",
        "prompt_instruction": "Write in a professional and formal tone.",
    },
    "casual": {
        "label": "Casual",
        "prompt_instruction": "Write in a friendly and casual tone.",
    },
    "concise": {
        "label": "Concise",
        "prompt_instruction": "Be brief and direct. Maximum 3 sentences.",
    },
    "empathetic": {
        "label": "Empathetic",
        "prompt_instruction": "Write with warmth and understanding.",
    },
}


def normalize_tone(value: Optional[str]) -> str:
    """
    Normalize a requested tone to a supported value.

    Fallback behavior:
    - None -> professional
    - empty string -> professional
    - unknown value -> professional
    """
    normalized = (value or "").strip().lower()
    return normalized if normalized in SUPPORTED_TONES else "professional"


def get_tone_instruction(tone: Optional[str]) -> str:
    """
    Return the prompt instruction for a normalized supported tone.
    Unknown values are normalized to 'professional'.
    """
    normalized = normalize_tone(tone)
    return SUPPORTED_TONES[normalized]["prompt_instruction"]


def list_supported_tones() -> list[dict]:
    """
    Return supported tones as API-friendly objects.

    Output shape:
    [
      {"code": "professional", "label": "Professional"},
      ...
    ]
    """
    return [
        {"code": code, "label": info["label"]}
        for code, info in SUPPORTED_TONES.items()
    ]
