import { EmailViewModel } from '@types';
import { deriveAiSummaryConfidence } from '@utils/deriveAiSummaryConfidence';

export type ThreadContextUrgencyLevel = 'high' | 'medium' | 'none';

export interface ThreadContextResult {
  threadDepth: number | null;
  threadHasAttachments: boolean | null;
  urgencyLevel: ThreadContextUrgencyLevel;
  daysSinceLastMessage: number | null;
  lastSenderIsCorrespondent: boolean | null;
  hasPendingReply: boolean | null;
}

type Input = Pick<
  EmailViewModel,
  | 'thread_count'
  | 'has_attachments'
  | 'category'
  | 'ai_summary_text'
  | 'ai_summary_is_fallback'
  | 'ai_summary_language'
  | 'ai_preferred_language'
> & {
  last_activity_iso?: string | null;
  last_sender?: string | null;
};

// Extracts a normalized lowercase email address from a plain address or
// "Display Name <email@domain>" form. Returns null if unusable.
function normalizeMailbox(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  const angleMatch = trimmed.match(/<([^>]+)>/);
  const addr = angleMatch ? angleMatch[1] : trimmed;
  const normalized = addr.toLowerCase().trim();
  return normalized.length > 0 && normalized.includes('@') ? normalized : null;
}

export function deriveThreadContext(email: Input, accountEmail?: string): ThreadContextResult {
  const threadDepth =
    typeof email.thread_count === 'number' && email.thread_count >= 1
      ? email.thread_count
      : 1;

  const threadHasAttachments =
    email.has_attachments === true
      ? true
      : email.has_attachments === false
      ? false
      : null;

  const confidence = deriveAiSummaryConfidence(email);
  // Trust / verification urgency only:
  // low AI-summary confidence means the user should verify before acting.
  // "high" is Financial + low confidence; "medium" is other low-confidence categories.
  // This is not a business-priority classifier.
  let urgencyLevel: ThreadContextUrgencyLevel = 'none';
  if (confidence.level === 'low') {
    urgencyLevel = email.category === 'Financial' ? 'high' : 'medium';
  }

  // daysSinceLastMessage: whole-day delta from last_activity_iso to now, clamped to >= 0
  let daysSinceLastMessage: number | null = null;
  if (email.last_activity_iso) {
    const ts = Date.parse(email.last_activity_iso);
    if (!Number.isNaN(ts)) {
      const delta = Math.floor((Date.now() - ts) / 86_400_000);
      daysSinceLastMessage = Math.max(0, delta);
    }
  }

  // lastSenderIsCorrespondent: true when last_sender is NOT the account owner
  let lastSenderIsCorrespondent: boolean | null = null;
  const normalizedLastSender = normalizeMailbox(email.last_sender);
  const normalizedAccountEmail = normalizeMailbox(accountEmail);
  if (normalizedLastSender !== null && normalizedAccountEmail !== null) {
    lastSenderIsCorrespondent = normalizedLastSender !== normalizedAccountEmail;
  }

  // hasPendingReply: requires both recency and polarity to be known
  let hasPendingReply: boolean | null = null;
  if (daysSinceLastMessage !== null && lastSenderIsCorrespondent !== null) {
    hasPendingReply = lastSenderIsCorrespondent;
  }

  return {
    threadDepth,
    threadHasAttachments,
    urgencyLevel,
    daysSinceLastMessage,
    lastSenderIsCorrespondent,
    hasPendingReply,
  };
}
