"""
Records user feedback on AI agent actions to the ai_feedback table.

Maps to the PROVEN ai_feedback schema exactly:
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  account_id TEXT NOT NULL
  feedback_type TEXT NOT NULL
  original_input TEXT NOT NULL
  original_output JSONB NOT NULL
  corrected_output JSONB
  rating SMALLINT
  used_as_example BOOLEAN NOT NULL DEFAULT FALSE
  created_at TIMESTAMPTZ DEFAULT NOW()

PRIVACY INVARIANT: original_input stores only the email subject, truncated to
MAX_SUBJECT_CHARS. Email body content is NEVER stored in this table.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_SUBJECT_CHARS = 500  # Hard cap — subject only, never email body


def record_feedback(
    store: Any,
    account_id: str,
    conversation_id: str,
    action_type: str,
    subject: str,
    outcome: str,
    rating: Optional[int] = None,
) -> None:
    """
    Write one ai_feedback row using the proven schema.

    Column mapping:
      feedback_type   ← action_type (e.g. "draft_reply")
      original_input  ← subject[:500] ONLY — never email body
      original_output ← {"conversation_id": ..., "outcome": ...} — no body content
      corrected_output← None
      rating          ← caller-provided 1–5 or None
      used_as_example ← True when outcome == "accepted"

    Feedback is best-effort. DB failure is logged as warning and never re-raised.
    """
    safe_subject = (subject or "")[:MAX_SUBJECT_CHARS]
    used_as_example = outcome == "accepted"
    try:
        store.client.table("ai_feedback").insert(
            {
                "account_id": account_id,
                "feedback_type": action_type,        # proven column: feedback_type TEXT NOT NULL
                "original_input": safe_subject,       # proven column: subject only, max 500 chars
                "original_output": {                  # proven column: JSONB NOT NULL
                    "conversation_id": conversation_id,
                    "outcome": outcome,
                },
                "corrected_output": None,             # proven column: JSONB (nullable)
                "rating": rating,                     # proven column: SMALLINT (nullable)
                "used_as_example": used_as_example,  # proven column: BOOLEAN NOT NULL DEFAULT FALSE
            }
        ).execute()
        logger.info(
            "[FEEDBACK] Recorded feedback_type=%s outcome=%s used_as_example=%s account=%s",
            action_type,
            outcome,
            used_as_example,
            account_id,
        )
    except Exception as e:
        logger.warning(
            "[FEEDBACK] Write failed (non-fatal): %s", type(e).__name__
        )
