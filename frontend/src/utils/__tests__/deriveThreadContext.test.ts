import { describe, it, expect } from 'vitest';
import { deriveThreadContext } from '@utils/deriveThreadContext';

// Produces 'low' confidence via deriveAiSummaryConfidence (fallback flag path).
const lowConfidence = {
  ai_summary_is_fallback: true as const,
  ai_summary_text: 'short',
  ai_summary_language: null,
  ai_preferred_language: null,
};

// Produces 'high' confidence: non-fallback, long text, matching languages.
const highConfidence = {
  ai_summary_is_fallback: false as const,
  ai_summary_text: 'A'.repeat(60),
  ai_summary_language: 'en' as const,
  ai_preferred_language: 'en' as const,
};

// ─────────────────────────────────────────────────────────────
// threadDepth
// ─────────────────────────────────────────────────────────────
describe('deriveThreadContext — threadDepth', () => {
  it('uses thread_count when it is a valid number >= 1', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 5,
      has_attachments: undefined,
      category: 'General',
    });
    expect(result.threadDepth).toBe(5);
  });

  it('falls back to 1 when thread_count is undefined', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: undefined,
      has_attachments: undefined,
      category: 'General',
    });
    expect(result.threadDepth).toBe(1);
  });

  it('falls back to 1 when thread_count is 0', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 0,
      has_attachments: undefined,
      category: 'General',
    });
    expect(result.threadDepth).toBe(1);
  });
});

// ─────────────────────────────────────────────────────────────
// threadHasAttachments
// ─────────────────────────────────────────────────────────────
describe('deriveThreadContext — threadHasAttachments', () => {
  it('returns true when has_attachments === true', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 1,
      has_attachments: true,
      category: 'General',
    });
    expect(result.threadHasAttachments).toBe(true);
  });

  it('returns false when has_attachments === false', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 1,
      has_attachments: false,
      category: 'General',
    });
    expect(result.threadHasAttachments).toBe(false);
  });

  it('returns null when has_attachments is undefined', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 1,
      has_attachments: undefined,
      category: 'General',
    });
    expect(result.threadHasAttachments).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────
// urgencyLevel
// ─────────────────────────────────────────────────────────────
describe('deriveThreadContext — urgencyLevel', () => {
  it('returns "high" when category is Financial and confidence is low', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 1,
      has_attachments: undefined,
      category: 'Financial',
    });
    expect(result.urgencyLevel).toBe('high');
  });

  it('returns "medium" when confidence is low and category is not Financial', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 1,
      has_attachments: undefined,
      category: 'Work',
    });
    expect(result.urgencyLevel).toBe('medium');
  });

  it('returns "none" when confidence is not low', () => {
    const result = deriveThreadContext({
      ...highConfidence,
      thread_count: 1,
      has_attachments: undefined,
      category: 'Financial',
    });
    expect(result.urgencyLevel).toBe('none');
  });
});

// ─────────────────────────────────────────────────────────────
// V1 deferred fields — null when inputs are missing
// ─────────────────────────────────────────────────────────────
describe('deriveThreadContext — null when V2 inputs absent', () => {
  const base = {
    ...lowConfidence,
    thread_count: 1,
    has_attachments: undefined,
    category: 'General' as const,
  };

  it('daysSinceLastMessage returns null when last_activity_iso is absent', () => {
    expect(deriveThreadContext(base).daysSinceLastMessage).toBeNull();
  });

  it('lastSenderIsCorrespondent returns null when last_sender is absent', () => {
    expect(deriveThreadContext(base).lastSenderIsCorrespondent).toBeNull();
  });

  it('hasPendingReply returns null when both V2 inputs are absent', () => {
    expect(deriveThreadContext(base).hasPendingReply).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────
// T1/T2: ai_summary_json.category takes precedence over legacy category
// ─────────────────────────────────────────────────────────────
describe('deriveThreadContext — ai_summary_json.category takes precedence (T1)', () => {
  it('returns "high" when ai_summary_json.category is FINANCIAL_LEGAL regardless of legacy category', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 1,
      has_attachments: undefined,
      category: 'Work',
      ai_summary_json: { overview: '', action_items: [], urgency: 'low', category: 'FINANCIAL_LEGAL' },
    });
    expect(result.urgencyLevel).toBe('high');
  });
});

describe('deriveThreadContext — ai_summary_json.category suppresses legacy Financial (T2)', () => {
  it('returns "medium" when ai_summary_json.category is CONTENT_INFO but legacy category is Financial', () => {
    const result = deriveThreadContext({
      ...lowConfidence,
      thread_count: 1,
      has_attachments: undefined,
      category: 'Financial',
      ai_summary_json: { overview: '', action_items: [], urgency: 'low', category: 'CONTENT_INFO' },
    });
    expect(result.urgencyLevel).toBe('medium');
  });
});

// ─────────────────────────────────────────────────────────────
// V2 activated fields
// ─────────────────────────────────────────────────────────────
describe('deriveThreadContext — V2 activated fields', () => {
  const baseV2 = {
    ...lowConfidence,
    thread_count: 2,
    has_attachments: false,
    category: 'Work' as const,
  };

  // 1. valid last_activity_iso produces a non-null daysSinceLastMessage
  it('daysSinceLastMessage is non-null for a valid last_activity_iso', () => {
    const result = deriveThreadContext({
      ...baseV2,
      last_activity_iso: new Date(Date.now() - 2 * 86_400_000).toISOString(),
      last_sender: 'correspondent@example.com',
    }, 'me@example.com');
    expect(result.daysSinceLastMessage).not.toBeNull();
    expect(result.daysSinceLastMessage).toBeGreaterThanOrEqual(0);
  });

  // 2. correspondent sent last message → lastSenderIsCorrespondent true, hasPendingReply true
  it('lastSenderIsCorrespondent is true and hasPendingReply is true when correspondent sent last', () => {
    const result = deriveThreadContext({
      ...baseV2,
      last_activity_iso: new Date(Date.now() - 86_400_000).toISOString(),
      last_sender: 'alice@example.com',
    }, 'me@example.com');
    expect(result.lastSenderIsCorrespondent).toBe(true);
    expect(result.hasPendingReply).toBe(true);
  });

  // 3. account owner sent last message → lastSenderIsCorrespondent false, hasPendingReply false
  it('lastSenderIsCorrespondent is false and hasPendingReply is false when account owner sent last', () => {
    const result = deriveThreadContext({
      ...baseV2,
      last_activity_iso: new Date(Date.now() - 3600_000).toISOString(),
      last_sender: 'me@example.com',
    }, 'me@example.com');
    expect(result.lastSenderIsCorrespondent).toBe(false);
    expect(result.hasPendingReply).toBe(false);
  });

  // 4. display-name "Name <email>" form is normalized correctly
  it('normalizes display-name format "Alice Example <alice@example.com>"', () => {
    const result = deriveThreadContext({
      ...baseV2,
      last_activity_iso: new Date(Date.now() - 86_400_000).toISOString(),
      last_sender: 'Alice Example <alice@example.com>',
    }, 'me@example.com');
    expect(result.lastSenderIsCorrespondent).toBe(true);
  });

  // 5. invalid last_activity_iso keeps recency and pending-reply null while polarity remains computable
  it('daysSinceLastMessage and hasPendingReply remain null while polarity remains computable when last_activity_iso is invalid', () => {
    const result = deriveThreadContext({
      ...baseV2,
      last_activity_iso: 'not-a-date',
      last_sender: 'alice@example.com',
    }, 'me@example.com');
    expect(result.daysSinceLastMessage).toBeNull();
    expect(result.lastSenderIsCorrespondent).toBe(true); // polarity still computable
    expect(result.hasPendingReply).toBeNull(); // needs recency
  });
});
