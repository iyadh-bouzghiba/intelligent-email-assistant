import { EmailViewModel } from '@types';
import { deriveAiSummaryConfidence } from '@utils/deriveAiSummaryConfidence';

type SpineInput = Pick<EmailViewModel,
  | 'thread_count'
  | 'has_attachments'
  | 'last_activity_iso'
  | 'last_sender'
  | 'category'
  | 'ai_summary_text'
  | 'ai_summary_is_fallback'
  | 'ai_summary_language'
  | 'ai_preferred_language'
  | 'is_read'
>;

export interface SpineSignalResult {
  urgencyLevel: 'high' | 'medium' | 'none';
  hasAttachments: boolean | null;
  daysSinceLastActivity: number | null;
  isPendingReply: boolean | null;
  threadDepth: number | null;
  hasAnySignal: boolean;
}

function normalizeMailbox(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const match = trimmed.match(/<([^>]+)>/);
  const address = (match ? match[1] : trimmed).trim().toLowerCase();
  return address.includes('@') ? address : null;
}

export function deriveSpineSignals(
  email: SpineInput,
  accountEmail: string,
): SpineSignalResult {
  const conf = deriveAiSummaryConfidence(email);
  // Trust / verification urgency only:
  // low AI-summary confidence means the user should verify before acting.
  // "high" is Financial + low confidence; "medium" is other low-confidence categories.
  // This is not a business-priority classifier.
  const urgencyLevel: SpineSignalResult['urgencyLevel'] =
    conf.level === 'low'
      ? email.category === 'Financial' ? 'high' : 'medium'
      : 'none';

  const hasAttachments =
    email.has_attachments === true ? true
    : email.has_attachments === false ? false
    : null;

  let daysSinceLastActivity: number | null = null;
  if (email.last_activity_iso) {
    const parsed = new Date(email.last_activity_iso);
    if (!isNaN(parsed.getTime())) {
      daysSinceLastActivity = Math.max(
        0,
        Math.floor((Date.now() - parsed.getTime()) / 86_400_000),
      );
    }
  }

  const normalizedLastSender = normalizeMailbox(email.last_sender);
  const normalizedAccountEmail = normalizeMailbox(accountEmail);
  const lastSenderIsCorrespondent =
    normalizedLastSender === null || normalizedAccountEmail === null
      ? null
      : normalizedLastSender !== normalizedAccountEmail;

  const isPendingReply =
    lastSenderIsCorrespondent === true && daysSinceLastActivity !== null && daysSinceLastActivity >= 1
      ? true
      : lastSenderIsCorrespondent === false
      ? false
      : null;

  const threadDepth =
    typeof email.thread_count === 'number' && email.thread_count >= 3
      ? email.thread_count
      : null;

  const hasAnySignal =
    urgencyLevel !== 'none' ||
    hasAttachments === true ||
    daysSinceLastActivity !== null ||
    threadDepth !== null;

  return {
    urgencyLevel,
    hasAttachments,
    daysSinceLastActivity,
    isPendingReply,
    threadDepth,
    hasAnySignal,
  };
}
