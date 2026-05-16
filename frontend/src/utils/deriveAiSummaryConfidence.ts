import { EmailViewModel } from '@types';

export type AiSummaryConfidenceLevel = 'high' | 'medium' | 'low';

export type AiSummaryConfidenceReason =
  | 'fallback_summary'
  | 'summary_too_short'
  | 'language_mismatch'
  | 'signal_incomplete';

export interface AiSummaryConfidenceResult {
  level: AiSummaryConfidenceLevel;
  reasons: AiSummaryConfidenceReason[];
  reviewRequired: boolean;
}

export function deriveAiSummaryConfidence(
  email: Pick<EmailViewModel, 'ai_summary_text' | 'ai_summary_is_fallback' | 'ai_summary_language' | 'ai_preferred_language'>
): AiSummaryConfidenceResult {
  const text = (email.ai_summary_text ?? '').trim();

  if (email.ai_summary_is_fallback === true) {
    return { level: 'low', reasons: ['fallback_summary'], reviewRequired: true };
  }

  if (!text || text.length < 50) {
    return { level: 'low', reasons: ['summary_too_short'], reviewRequired: true };
  }

  if (!email.ai_summary_language || !email.ai_preferred_language) {
    return { level: 'medium', reasons: ['signal_incomplete'], reviewRequired: false };
  }

  if (email.ai_summary_language !== email.ai_preferred_language) {
    return { level: 'medium', reasons: ['language_mismatch'], reviewRequired: false };
  }

  return { level: 'high', reasons: [], reviewRequired: false };
}
