import { EmailViewModel } from '@types';
import { deriveAiSummaryConfidence } from '@utils/deriveAiSummaryConfidence';

export type ThreadContextUrgencyLevel = 'high' | 'medium' | 'none';

export interface ThreadContextResult {
  threadDepth: number | null;
  threadHasAttachments: boolean | null;
  urgencyLevel: ThreadContextUrgencyLevel;
  // Representative-row date is not approved as true thread-last-message recency
  // in current payload semantics: the backend strips _latest_activity before
  // returning, and the representative row carries only the most-recent inbox
  // message date, not the absolute last activity across sent + received.
  daysSinceLastMessage: number | null;
  // Representative-row sender is not approved as true thread-last-actor truth
  // in current payload semantics: the representative is the most recent
  // received message; a user reply would not update this field.
  lastSenderIsCorrespondent: boolean | null;
  // Depends on unsupported recency and last-actor truth — both deferred in V1.
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
>;

export function deriveThreadContext(email: Input): ThreadContextResult {
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
  let urgencyLevel: ThreadContextUrgencyLevel = 'none';
  if (confidence.level === 'low') {
    urgencyLevel = email.category === 'Financial' ? 'high' : 'medium';
  }

  return {
    threadDepth,
    threadHasAttachments,
    urgencyLevel,
    daysSinceLastMessage: null,
    lastSenderIsCorrespondent: null,
    hasPendingReply: null,
  };
}
