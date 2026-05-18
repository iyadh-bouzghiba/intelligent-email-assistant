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
// Deferred fields
// ─────────────────────────────────────────────────────────────
describe('deriveThreadContext — deferred fields', () => {
  const base = {
    ...lowConfidence,
    thread_count: 1,
    has_attachments: undefined,
    category: 'General' as const,
  };

  it('daysSinceLastMessage returns null', () => {
    expect(deriveThreadContext(base).daysSinceLastMessage).toBeNull();
  });

  it('lastSenderIsCorrespondent returns null', () => {
    expect(deriveThreadContext(base).lastSenderIsCorrespondent).toBeNull();
  });

  it('hasPendingReply returns null', () => {
    expect(deriveThreadContext(base).hasPendingReply).toBeNull();
  });
});
