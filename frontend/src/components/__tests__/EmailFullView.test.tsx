/**
 * P3.5-R3C-P2 — Deterministic proof: EmailFullView translation render contract.
 *
 * Three invariants tested:
 *   1. structured success        → translated-state bar present, fallback banner absent
 *   2. simplified fallback       → disclosure banner present, no raw technical codes exposed
 *   3. structured contract mismatch guard → safe fallback path, disclosure present, not silent success
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { EmailFullView } from '../EmailFullView';
import type { EmailViewModel } from '@types';

// ---------------------------------------------------------------------------
// react-i18next mock — deterministic English strings, no i18n initialisation
// ---------------------------------------------------------------------------
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) => {
      const map: Record<string, string> = {
        'modal.fallback_translation_title': 'Simplified translated view',
        'modal.fallback_translation_notice': 'Some original formatting could not be preserved.',
        'modal.translated_to': `Translated to ${opts?.language ?? ''}`,
        'modal.view_original': 'View original',
        'modal.translate_to': `Translate to ${opts?.language ?? ''}`,
        'modal.translating_to': `Translating to ${opts?.language ?? ''}...`,
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
      return map[key] ?? key;
    },
    i18n: { language: 'en' },
  }),
}));

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

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const mockEmail: EmailViewModel = {
  account: 'test@example.com',
  subject: 'Test Subject',
  sender: 'sender@example.com',
  date: '2025-01-01',
  priority: 'Medium',
  category: 'Work',
  should_alert: false,
  summary: 'Test email summary',
  action: 'None',
  gmail_message_id: 'msg-test-001',
};

const actionItemsRef = { current: null } as React.RefObject<HTMLDivElement>;
const noop = () => {};

// Fetch stub that never resolves — the /rendered endpoint is irrelevant to
// translation rendering (which is fully prop-driven). A never-resolving fetch
// prevents any async state updates after the initial render, avoiding the
// act(async () => {}) hang that occurs in React 18 concurrent mode when
// floating promises are still pending at assertion time.
const fetchNeverResolves = vi.fn().mockImplementation(() => new Promise<Response>(() => {}));

// ---------------------------------------------------------------------------

describe('EmailFullView — translation render contract', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchNeverResolves);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // -------------------------------------------------------------------------
  // Case 1: structured success
  // Props: structured_html / preserved / translatedBodyHtml present
  // Expected: translated-state bar renders; fallback disclosure banner absent
  // -------------------------------------------------------------------------
  it('structured success: translated-state bar renders and fallback banner is absent', async () => {
    render(
      <EmailFullView
        email={mockEmail}
        actionItemsRef={actionItemsRef}
        onBackToSummary={noop}
        translationActive={true}
        translationMode="structured_html"
        translationFidelity="preserved"
        translatedBodyHtml="<p>Translated HTML content</p>"
        showTranslateControls={true}
        translateState="translated"
        translateLanguageLabel="English"
        onTranslateToggle={noop}
      />
    );

    // Translation rendering is prop-driven; assertions are synchronous after render.
    // Translated-state bar must render
    expect(screen.getByText('Translated to English')).toBeInTheDocument();

    // Fallback disclosure banner must NOT be present
    expect(screen.queryByText('Simplified translated view')).not.toBeInTheDocument();
    expect(
      screen.queryByText('Some original formatting could not be preserved.')
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Case 2: simplified fallback
  // Props: text_fallback / simplified / translatedBody present
  // Expected: disclosure banner renders with safe localized text;
  //           no raw technical prop codes exposed to the user
  // -------------------------------------------------------------------------
  it('simplified fallback: disclosure banner renders with safe localized text, no raw codes', async () => {
    render(
      <EmailFullView
        email={mockEmail}
        actionItemsRef={actionItemsRef}
        onBackToSummary={noop}
        translationActive={true}
        translationMode="text_fallback"
        translationFidelity="simplified"
        translatedBody="This is the plain-text fallback translation of the email body."
        showTranslateControls={true}
        translateState="translated"
        translateLanguageLabel="English"
        onTranslateToggle={noop}
      />
    );

    // Disclosure banner must render with both title and notice
    expect(screen.getByText('Simplified translated view')).toBeInTheDocument();
    expect(
      screen.getByText('Some original formatting could not be preserved.')
    ).toBeInTheDocument();

    // The plain-text body content must be visible
    expect(
      screen.getByText('This is the plain-text fallback translation of the email body.')
    ).toBeInTheDocument();

    // No raw technical reason code strings must be rendered
    expect(screen.queryByText('text_fallback')).not.toBeInTheDocument();
    expect(screen.queryByText('simplified')).not.toBeInTheDocument();
    expect(screen.queryByText(/translation_reason_code/i)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Case 3: structured contract mismatch guard
  // Props: structured_html / preserved / translatedBodyHtml = null / translatedBody present
  // Expected: safe fallback text renders; disclosure banner present;
  //           component does NOT silently behave like structured success
  // -------------------------------------------------------------------------
  it('structured contract mismatch guard: fallback path and disclosure render, not silent success', async () => {
    render(
      <EmailFullView
        email={mockEmail}
        actionItemsRef={actionItemsRef}
        onBackToSummary={noop}
        translationActive={true}
        translationMode="structured_html"
        translationFidelity="preserved"
        translatedBodyHtml={null}
        translatedBody="Mismatch guard activated — plain text fallback rendered."
        showTranslateControls={true}
        translateState="translated"
        translateLanguageLabel="English"
        onTranslateToggle={noop}
      />
    );

    // Safe fallback text path must render the plain text
    expect(
      screen.getByText('Mismatch guard activated — plain text fallback rendered.')
    ).toBeInTheDocument();

    // Fallback disclosure banner must render — mismatch must NOT be silent
    expect(screen.getByText('Simplified translated view')).toBeInTheDocument();
    expect(
      screen.getByText('Some original formatting could not be preserved.')
    ).toBeInTheDocument();

    // The structured HTML content must not appear — no silent structured-success path
    expect(screen.queryByText('Translated HTML content')).not.toBeInTheDocument();
  });
});
