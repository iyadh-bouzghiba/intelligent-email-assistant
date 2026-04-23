"""
Approval gate for agent actions — BL-08/BL-09.

Checks audit_log for an explicit user consent entry:
  action = 'agent_consent'
  resource = account_id
  user_approved = TRUE

Fails closed: missing row, absent column, or any DB error → returns False.

PREREQUISITE: The SQL patch
  ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS user_approved BOOLEAN NOT NULL DEFAULT FALSE;
  ALTER TABLE public.audit_log ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL;
must be applied before this gate can pass for any account.
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.infrastructure.supabase_store import SupabaseStore

logger = logging.getLogger(__name__)

CONSENT_ACTION = "agent_consent"


def check_agent_approved(store: "SupabaseStore", account_id: str) -> bool:
    """
    Returns True ONLY if audit_log contains a row where:
      action='agent_consent', resource=account_id, user_approved=TRUE.

    Fails closed on:
    - No matching row (consent never granted)
    - user_approved column missing (SQL patch not applied)
    - Any DB error
    """
    try:
        response = (
            store.client.table("audit_log")
            .select("user_approved")
            .eq("action", CONSENT_ACTION)
            .eq("resource", account_id)
            .eq("user_approved", True)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return bool(rows and rows[0].get("user_approved") is True)
    except Exception as e:
        logger.warning(
            "[APPROVAL-GATE] DB check failed — blocking action for %s: %s",
            account_id,
            type(e).__name__,
        )
        return False  # Fail closed
