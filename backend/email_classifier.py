"""Deterministic, rules-only universal email classifier.

No AI, no network, no external dependencies — pure Python stdlib.
First match in UNIVERSAL_CATEGORY_PRIORITY wins.
"""

import re
from typing import Optional

__all__ = [
    "UNIVERSAL_CATEGORY_PRIORITY",
    "classify_email_category",
]

UNIVERSAL_CATEGORY_PRIORITY: tuple[str, ...] = (
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

# ---------------------------------------------------------------------------
# Keyword groups — each tuple is OR-matched against the normalized text blob
# ---------------------------------------------------------------------------

_SECURITY_KEYWORDS: tuple = (
    "password reset",
    "reset your password",
    "verify your identity",
    "verification code",
    "one-time code",
    "one time code",
    "two-factor",
    "2fa",
    r"\bmfa\b",
    "sign-in attempt",
    "login attempt",
    "login alert",
    "suspicious activity",
    "unusual activity",
    "new device login",
    "account locked",
    "unlock account",
    "security alert",
    r"\bbreach\b",
    "compromised account",
    "permission change",
    "access change",
    "recovery code",
    "backup code",
    "security notification",
)

_FINANCIAL_KEYWORDS: tuple = (
    r"\binvoice\b",
    r"\breceipt\b",
    r"\bstatement\b",
    "balance due",
    "payment due",
    "payment received",
    r"\bpaid\b",
    r"\bbilling\b",
    "wire transfer",
    "bank transfer",
    r"\bquote\b",
    r"\bquotation\b",
    r"\bestimate\b",
    r"\bcontract\b",
    r"\bagreement\b",
    "legal notice",
    r"\bcompliance\b",
    r"\bregulation\b",
    r"\bregulatory\b",
    r"\btax\b",
    r"\bvat\b",
    "purchase order",
    r"\bpo\b",
    "renewal terms",
    "subscription renewal",
)

_ACTION_KEYWORDS: tuple = (
    "please review",
    "please approve",
    "approval needed",
    "action required",
    "respond by",
    "reply by",
    "complete by",
    "due by",
    r"\bdeadline\b",
    "before eod",
    "before cob",
    "please sign",
    "sign this",
    "please confirm",
    "please submit",
    "please fill out",
    "fill out the form",
    "please upload",
    "please send",
    "urgent response needed",
    "needs your response",
)

_SCHEDULING_KEYWORDS: tuple = (
    "meeting invite",
    "calendar invite",
    "calendar event",
    r"\bcalendar\b",
    r"\breschedule\b",
    r"\bavailability\b",
    "available at",
    "meeting confirmed",
    r"\bappointment\b",
    "schedule a meeting",
    "schedule a call",
    "join zoom",
    "join teams",
    "google meet",
    "call tomorrow",
    "call at",
    "event starts",
)

_PROJECT_KEYWORDS: tuple = (
    r"\bsprint\b",
    r"\bticket\b",
    r"\bjira\b",
    "task update",
    "status update",
    "project update",
    "deployment update",
    "release update",
    "code review",
    "pull request",
    r"\bpr\b",
    "merge request",
    "standup notes",
    "meeting notes",
    "action log",
    r"\bblocker\b",
    r"\bmilestone\b",
    r"\broadmap\b",
    r"\bdeliverable\b",
    "bug fix",
)

_AUTOMATED_KEYWORDS: tuple = (
    "no-reply",
    "noreply",
    "do-not-reply",
    r"\bnotification\b",
    "ci failed",
    "ci passed",
    "build failed",
    "build passed",
    "monitor alert",
    "incident alert",
    "uptime alert",
    "workflow run",
    "form submission",
    "crm update",
    "automated report",
    "system generated",
    "server status",
    "backup completed",
    "job failed",
    "job succeeded",
)

_CONTENT_KEYWORDS: tuple = (
    r"\bnewsletter\b",
    r"\bdigest\b",
    "weekly update",
    "monthly update",
    r"\bannouncement\b",
    "product update",
    "release notes",
    r"\bchangelog\b",
    r"\bblog\b",
    "article roundup",
    "research report",
    r"\binsights\b",
    "industry update",
    r"\bunsubscribe\b",
    "read more",
    "top stories",
)

_PERSONAL_KEYWORDS: tuple = (
    r"\bbirthday\b",
    r"\bparty\b",
    r"\bdinner\b",
    r"\bfamily\b",
    r"\bfriend\b",
    r"\breunion\b",
    r"\bcongratulations\b",
    r"\bcongrats\b",
    r"\bwedding\b",
    "holiday plans",
    "personal invitation",
    "social event",
    "community meetup",
)

_CONVERSATION_KEYWORDS: tuple = (
    r"\bre:",
    r"\bfw:",
    r"\bthanks\b",
    "thank you",
    "got it",
    "sounds good",
    "let's discuss",
    "following up",
    "checking in",
    "quick question",
    "can we talk",
    "appreciate it",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_text(subject: str, sender: str, body_snippet: str) -> str:
    """Combine fields into a single lowercase, whitespace-normalized string."""
    parts = [subject or "", sender or "", body_snippet or ""]
    combined = " ".join(parts)
    combined = combined.lower()
    combined = re.sub(r"\s+", " ", combined).strip()
    return combined


def _matches_any(text: str, patterns: tuple) -> bool:
    """Return True if any pattern in *patterns* matches *text*."""
    for pattern in patterns:
        try:
            if re.search(pattern, text):
                return True
        except re.error:
            if pattern in text:
                return True
    return False


def _is_security_account(text: str) -> bool:
    """Match SECURITY_ACCOUNT patterns."""
    return _matches_any(text, _SECURITY_KEYWORDS)


def _is_financial_legal(text: str) -> bool:
    """Match FINANCIAL_LEGAL patterns."""
    return _matches_any(text, _FINANCIAL_KEYWORDS)


def _is_action_required(text: str) -> bool:
    """Match ACTION_REQUIRED patterns."""
    return _matches_any(text, _ACTION_KEYWORDS)


def _is_scheduling(text: str) -> bool:
    """Match SCHEDULING patterns."""
    return _matches_any(text, _SCHEDULING_KEYWORDS)


def _is_project_work(text: str) -> bool:
    """Match PROJECT_WORK patterns."""
    return _matches_any(text, _PROJECT_KEYWORDS)


def _is_automated_system(text: str) -> bool:
    """Match AUTOMATED_SYSTEM patterns."""
    return _matches_any(text, _AUTOMATED_KEYWORDS)


def _is_content_info(text: str) -> bool:
    """Match CONTENT_INFO patterns."""
    return _matches_any(text, _CONTENT_KEYWORDS)


def _is_personal_social(text: str) -> bool:
    """Match PERSONAL_SOCIAL patterns."""
    return _matches_any(text, _PERSONAL_KEYWORDS)


def _is_conversation(text: str, thread_count: Optional[int]) -> bool:
    """Match CONVERSATION patterns; thread_count >= 3 is a soft signal."""
    if _matches_any(text, _CONVERSATION_KEYWORDS):
        return True
    if thread_count is not None and thread_count >= 3:
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_email_category(
    subject: str,
    sender: str,
    body_snippet: str,
    thread_count: Optional[int] = None,
) -> str:
    """Classify an email into one of UNIVERSAL_CATEGORY_PRIORITY categories.

    Uses deterministic, rule-based keyword matching only.
    First match wins; returns UNCATEGORIZED when nothing matches.
    Never raises on empty or None-like inputs.
    """
    try:
        text = _normalize_text(
            subject or "",
            sender or "",
            body_snippet or "",
        )

        if _is_security_account(text):
            return "SECURITY_ACCOUNT"
        if _is_financial_legal(text):
            return "FINANCIAL_LEGAL"
        if _is_action_required(text):
            return "ACTION_REQUIRED"
        if _is_scheduling(text):
            return "SCHEDULING"
        if _is_project_work(text):
            return "PROJECT_WORK"
        if _is_automated_system(text):
            return "AUTOMATED_SYSTEM"
        if _is_content_info(text):
            return "CONTENT_INFO"
        if _is_personal_social(text):
            return "PERSONAL_SOCIAL"
        if _is_conversation(text, thread_count):
            return "CONVERSATION"

        return "UNCATEGORIZED"

    except Exception:
        return "UNCATEGORIZED"
