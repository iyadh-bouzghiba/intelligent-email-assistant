"""
Retrieves qualifying ai_feedback rows as few-shot examples for agent prompts.

Only rows with used_as_example=TRUE are returned.
Queries ONLY proven columns: account_id, feedback_type, used_as_example,
original_input, original_output.
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MAX_EXAMPLES = 3  # Cap to keep prompt size bounded


def get_fewshot_examples(
    store: Any,
    account_id: str,
    action_type: str,
) -> List[Dict[str, Any]]:
    """
    Return up to MAX_EXAMPLES qualifying ai_feedback rows for prompt injection.

    Filters by:
      account_id    = account_id          (proven column: TEXT NOT NULL)
      feedback_type = action_type         (proven column: TEXT NOT NULL)
      used_as_example = TRUE              (proven column: BOOLEAN NOT NULL DEFAULT FALSE)

    Selects:
      original_input   — email subject, used directly in prompt construction
      original_output  — JSONB metadata (conversation_id, outcome)

    Returns empty list on failure — never blocks agent action.
    """
    try:
        response = (
            store.client.table("ai_feedback")
            .select("original_input,original_output")
            .eq("account_id", account_id)
            .eq("feedback_type", action_type)    # proven column: feedback_type TEXT NOT NULL
            .eq("used_as_example", True)         # proven column: used_as_example BOOLEAN NOT NULL
            .order("created_at", desc=True)
            .limit(MAX_EXAMPLES)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.warning("[FEWSHOT] Fetch failed (non-fatal): %s", type(e).__name__)
        return []
