/**
 * SENT-TAB-REPAIR-01 — Deterministic proof: rendered fetch account_id behavior.
 *
 * Three invariants tested:
 *   1. Fetch URL includes account_id when email.account is present
 *   2. Fetch URL omits account_id when email.account is absent
 *   3. 404 response surfaces modal.email_load_failed error text
 */
import React from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { EmailFullView } from '../EmailFullView';
import type { EmailViewModel } from '@types';

// ---------------------------------------------------------------------------
// react-i18next mock — deterministic English strings, no i18n initialisation
// ---------------------------------------------------------------------------
// t is defined ONCE in the factory — stable reference across renders.
// The effect dep array includes `t`; an unstable reference would re-run the
// effect on every render, aborting the in-flight controller before the error
// catch block can fire setRenderError.
vi.mock('react-i18next', () => {
  const _map: Record<string, string> = {
    'modal.email_load_failed': 'Could not load this message.',
    'modal.fallback_translation_title': 'Simplified translated view',
    'modal.fallback_translation_notice': 'Some original formatting could not be preserved.',
    'modal.view_original': 'View original',
    'modal.translation_failed_try_again': 'Translation failed. Try again.',
    'modal.full_message': 'Full message',
    'modal.sent_message': 'Sent message',
    'modal.back_to_summary': 'Back to summary',
    'modal.back_to_outbound_preview': 'Back to outbound preview',
    'modal.loading_inline_assets': 'Loading...',
    'modal.loading_sent_message_content': 'Loading sent message...',
    'modal.no_message_body': 'No message body.',
    'modal.no_sent_message_body': 'No sent message body.',
    'modal.ai_analysis': 'AI Analysis',
    'modal.action_items': 'Action items',
    'modal.urgency_label': 'Urgency:',
    'modal.refresh_ai_summary': 'Refresh AI summary',
    'ai_summary_category.label': 'Category:',
    'modal.summary_request_queued': 'Summary request queued',
    'modal.linked_files': 'Linked files',
    'modal.open_in_docs': 'Open in Docs',
    'modal.open_in_sheets': 'Open in Sheets',
    'modal.open_in_slides': 'Open in Slides',
    'modal.open_in_drive': 'Open in Drive',
    'languages.english': 'English',
    'inbox.urgency.high': 'High',
    'inbox.urgency.medium': 'Medium',
    'inbox.urgency.low': 'Low',
  };
  const t = (key: string, opts?: Record<string, string>) => {
    if (key === 'modal.translated_to') return `Translated to ${opts?.language ?? ''}`;
    if (key === 'modal.translate_to') return `Translate to ${opts?.language ?? ''}`;
    if (key === 'modal.translating_to') return `Translating to ${opts?.language ?? ''}...`;
    return _map[key] ?? key;
  };
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
  };
});

// ---------------------------------------------------------------------------
// lucide-react — stubs so SVG rendering doesn't interfere with text assertions
// ---------------------------------------------------------------------------
vi.mock('lucide-react', () => ({
  AlertTriangle: () => null,
  ExternalLink: () => null,
  Globe: () => null,
  RefreshCw: () => null,
  Sparkles: () => null,
}));

// ---------------------------------------------------------------------------
// Child components not under test — stub to isolate EmailFullView logic
// ---------------------------------------------------------------------------
vi.mock('../AttachmentStrip', () => ({
  AttachmentStrip: () => null,
}));

vi.mock('../ImageLightbox', () => ({
  ImageLightbox: () => null,
}));

vi.mock('../AiSummaryConfidence', () => ({
  default: () => null,
}));

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const baseEmail: EmailViewModel = {
  account: 'test@gmail.com',
  subject: 'Test Subject',
  sender: 'sender@example.com',
  date: '2025-01-01',
  priority: 'Medium',
  category: 'Work',
  should_alert: false,
  summary: 'Test summary',
  action: 'None',
  gmail_message_id: 'msg-test-001',
};

const actionItemsRef = { current: null } as React.RefObject<HTMLDivElement>;
const noop = () => {};

const fakeRenderedPayload = {
  gmail_message_id: 'msg-test-001',
  body_html: null,
  body_text: 'Hello',
  attachments: [],
  linked_files: [],
};

// ---------------------------------------------------------------------------

describe('EmailFullView — rendered fetch account_id behavior', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  // -------------------------------------------------------------------------
  // Test 1: account present → URL contains encoded account_id
  // -------------------------------------------------------------------------
  it('rendered fetch includes account_id when email.account present', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(fakeRenderedPayload),
    });
    vi.stubGlobal('fetch', mockFetch);

    render(
      <EmailFullView
        email={{ ...baseEmail, account: 'test@gmail.com', gmail_message_id: 'msg-test-001' }}
        actionItemsRef={actionItemsRef}
        onBackToSummary={noop}
      />
    );

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());

    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain('/api/emails/msg-test-001/rendered?account_id=test%40gmail.com');
  });

  // -------------------------------------------------------------------------
  // Test 2: account absent → URL has no account_id param
  // -------------------------------------------------------------------------
  it('rendered fetch omits account_id when email.account absent', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(fakeRenderedPayload),
    });
    vi.stubGlobal('fetch', mockFetch);

    render(
      <EmailFullView
        email={{ ...baseEmail, account: undefined as unknown as string, gmail_message_id: 'msg-test-001' }}
        actionItemsRef={actionItemsRef}
        onBackToSummary={noop}
      />
    );

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());

    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain('/api/emails/msg-test-001/rendered');
    expect(url).not.toContain('account_id');
  });

  // -------------------------------------------------------------------------
  // Test 3: fetch returns 404 → modal.email_load_failed text is visible
  // -------------------------------------------------------------------------
  it('shows email_load_failed message on rendered 404', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 404,
    });
    vi.stubGlobal('fetch', mockFetch);

    render(
      <EmailFullView
        email={{ ...baseEmail, account: 'test@gmail.com', gmail_message_id: 'msg-test-001' }}
        actionItemsRef={actionItemsRef}
        onBackToSummary={noop}
      />
    );

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());

    // Drain the microtask queue so the fetch response chain (catch → setRenderError)
    // runs and React commits the state update before we assert the DOM.
    await act(async () => { await Promise.resolve(); });

    expect(
      await screen.findByText('Could not load this message.', {}, { timeout: 3000 })
    ).toBeInTheDocument();
  });
});
