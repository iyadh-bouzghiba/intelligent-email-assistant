import { describe, it, expect, vi, afterEach } from 'vitest';
import { deriveSpineSignals } from '@utils/deriveSpineSignals';

type SpineInput = Parameters<typeof deriveSpineSignals>[0];

const defaults: SpineInput = {
  category: 'General',
  ai_summary_text: 'A'.repeat(60),
  ai_summary_is_fallback: false,
  ai_summary_language: 'en',
  ai_preferred_language: 'en',
  thread_count: 1,
  has_attachments: false,
  last_activity_iso: null,
  last_sender: null,
  is_read: true,
};

const makeInput = (overrides: Partial<SpineInput> = {}): SpineInput => ({
  ...defaults,
  ...overrides,
});

const ACCOUNT = 'me@test.com';
const FIXED_NOW = new Date('2024-06-15T12:00:00.000Z').getTime();

afterEach(() => {
  vi.useRealTimers();
});

describe('deriveSpineSignals — urgencyLevel', () => {
  it('returns "high" for Financial category with low-confidence summary', () => {
    const result = deriveSpineSignals(
      makeInput({ ai_summary_is_fallback: true, category: 'Financial' }),
      ACCOUNT,
    );
    expect(result.urgencyLevel).toBe('high');
  });

  it('returns "medium" for low-confidence summary with non-Financial category', () => {
    const result = deriveSpineSignals(
      makeInput({ ai_summary_is_fallback: true, category: 'Work' }),
      ACCOUNT,
    );
    expect(result.urgencyLevel).toBe('medium');
  });

  it('returns "none" for high-confidence summary', () => {
    const result = deriveSpineSignals(makeInput(), ACCOUNT);
    expect(result.urgencyLevel).toBe('none');
  });
});

describe('deriveSpineSignals — daysSinceLastActivity', () => {
  it('returns 1 when last_activity_iso is exactly one day earlier', () => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_NOW);
    const yesterday = new Date(FIXED_NOW - 86_400_000).toISOString();
    const result = deriveSpineSignals(
      makeInput({ last_activity_iso: yesterday }),
      ACCOUNT,
    );
    expect(result.daysSinceLastActivity).toBe(1);
  });

  it('clamps daysSinceLastActivity to 0 for a future last_activity_iso', () => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_NOW);
    const tomorrow = new Date(FIXED_NOW + 86_400_000).toISOString();
    const result = deriveSpineSignals(
      makeInput({ last_activity_iso: tomorrow }),
      ACCOUNT,
    );
    expect(result.daysSinceLastActivity).toBe(0);
  });
});

describe('deriveSpineSignals — isPendingReply', () => {
  it('returns true when correspondent sent last and activity is >= 1 day ago', () => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_NOW);
    const twoDaysAgo = new Date(FIXED_NOW - 2 * 86_400_000).toISOString();
    const result = deriveSpineSignals(
      makeInput({ last_sender: 'other@test.com', last_activity_iso: twoDaysAgo }),
      ACCOUNT,
    );
    expect(result.isPendingReply).toBe(true);
  });

  it('returns false when display-name sender normalizes to the account email', () => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_NOW);
    const yesterday = new Date(FIXED_NOW - 86_400_000).toISOString();
    const result = deriveSpineSignals(
      makeInput({
        last_sender: 'Alice Example < alice@example.com >',
        last_activity_iso: yesterday,
      }),
      'alice@example.com',
    );
    expect(result.isPendingReply).toBe(false);
  });
});

describe('deriveSpineSignals — threadDepth', () => {
  it('returns null when thread_count is less than 3', () => {
    const result = deriveSpineSignals(makeInput({ thread_count: 2 }), ACCOUNT);
    expect(result.threadDepth).toBeNull();
  });

  it('returns the thread_count value when it is >= 3', () => {
    const result = deriveSpineSignals(makeInput({ thread_count: 7 }), ACCOUNT);
    expect(result.threadDepth).toBe(7);
  });
});

describe('deriveSpineSignals — hasAnySignal', () => {
  it('returns false when all defaults produce no active signals', () => {
    const result = deriveSpineSignals(makeInput(), ACCOUNT);
    expect(result.hasAnySignal).toBe(false);
  });
});

// S1: ai_summary_json.category takes precedence over legacy email.category
describe('deriveSpineSignals — ai_summary_json.category takes precedence (S1)', () => {
  it('returns "high" when ai_summary_json.category is FINANCIAL_LEGAL regardless of legacy category', () => {
    const result = deriveSpineSignals(
      makeInput({
        ai_summary_is_fallback: true,
        ai_summary_json: { overview: '', action_items: [], urgency: 'low', category: 'FINANCIAL_LEGAL' },
        category: 'Work',
      }),
      ACCOUNT,
    );
    expect(result.urgencyLevel).toBe('high');
  });
});

// S2: ai_summary_json.category overrides legacy Financial when it is a non-financial category
describe('deriveSpineSignals — ai_summary_json.category suppresses legacy Financial (S2)', () => {
  it('returns "medium" (not "high", not "none") when ai_summary_json.category is CONTENT_INFO but legacy category is Financial', () => {
    const result = deriveSpineSignals(
      makeInput({
        ai_summary_is_fallback: true,
        ai_summary_json: { overview: '', action_items: [], urgency: 'low', category: 'CONTENT_INFO' },
        category: 'Financial',
      }),
      ACCOUNT,
    );
    expect(result.urgencyLevel).toBe('medium');
    expect(result.urgencyLevel).not.toBe('high');
    expect(result.urgencyLevel).not.toBe('none');
  });
});
