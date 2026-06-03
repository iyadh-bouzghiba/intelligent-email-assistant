/**
 * EmailQuickView — AI summary category rendering contract.
 *
 * Invariants:
 *   1. category present → category label + translated category string rendered
 *   2. category absent  → category label not rendered, no placeholder
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { EmailQuickView } from '../EmailQuickView';
import type { EmailViewModel } from '@types';

// ---------------------------------------------------------------------------
// react-i18next — deterministic English strings
// ---------------------------------------------------------------------------
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'modal.ai_analysis': 'AI Analysis',
        'modal.urgency_label': 'Urgency:',
        'modal.action_items': 'Action items',
        'modal.preview': 'Preview',
        'modal.outbound_preview': 'Outbound preview',
        'modal.read_full_email': 'Read full email',
        'modal.no_preview': 'No preview available.',
        'modal.no_outbound_preview': 'No outbound preview.',
        'modal.sent_preview_notice': 'Sent preview notice.',
        'modal.summary_generating': 'Generating summary…',
        'modal.ask_ai_assistant': 'Ask AI Assistant',
        'inbox.urgency.high': 'High',
        'inbox.urgency.medium': 'Medium',
        'inbox.urgency.low': 'Low',
        'ai_summary_category.label': 'Category:',
        'category.action_required': 'Action Required',
        'category.informational': 'Informational',
        'category.meeting': 'Meeting',
        'category.finance': 'Finance',
        'category.travel': 'Travel',
        'category.alert': 'Alert',
      };
      return map[key] ?? (opts?.defaultValue as string) ?? key;
    },
    i18n: { language: 'en' },
  }),
}));

// ---------------------------------------------------------------------------
// lucide-react — stubs so SVG rendering doesn't pollute text assertions
// ---------------------------------------------------------------------------
vi.mock('lucide-react', () => ({
  Sparkles: () => null,
  Bot: () => null,
}));

// ---------------------------------------------------------------------------
// AiSummaryConfidence — not under test; stub to isolate QuickView logic
// ---------------------------------------------------------------------------
vi.mock('../AiSummaryConfidence', () => ({
  default: () => null,
}));

// ---------------------------------------------------------------------------
// normalizeBodyText — pass-through so no body text is mangled
// ---------------------------------------------------------------------------
vi.mock('@utils/normalizeBodyText', () => ({
  normalizeBodyText: (s: string) => s,
}));

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const baseEmail: EmailViewModel = {
  account: 'test@example.com',
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

// ---------------------------------------------------------------------------

describe('EmailQuickView — AI summary category rendering', () => {
  it('renders category label and translated category when email.ai_summary_json.category is present', () => {
    const email: EmailViewModel = {
      ...baseEmail,
      ai_summary_text: 'This needs immediate attention.',
      ai_summary_json: {
        overview: 'Needs action',
        action_items: [],
        urgency: 'high',
        category: 'ACTION_REQUIRED',
      },
    };

    render(
      <EmailQuickView
        email={email}
        actionItemsRef={actionItemsRef}
        onReadFull={noop}
      />
    );

    expect(screen.getByText('Category:')).toBeInTheDocument();
    expect(screen.getByText('Action Required')).toBeInTheDocument();
  });

  it('omits category label when email.ai_summary_json.category is absent', () => {
    const email: EmailViewModel = {
      ...baseEmail,
      ai_summary_text: 'Summary without category.',
      ai_summary_json: {
        overview: 'No category set',
        action_items: [],
        urgency: 'low',
      },
    };

    render(
      <EmailQuickView
        email={email}
        actionItemsRef={actionItemsRef}
        onReadFull={noop}
      />
    );

    expect(screen.queryByText('Category:')).not.toBeInTheDocument();
  });

  it('renders category as sole metadata row when urgency is absent', () => {
    const email: EmailViewModel = {
      ...baseEmail,
      ai_summary_text: 'Project update summary.',
      // Cast omits urgency to simulate partial/legacy runtime data where
      // the field is missing; proves category renders without urgency present.
      ai_summary_json: {
        overview: 'Project update',
        action_items: [],
        category: 'PROJECT_WORK',
      } as unknown as EmailViewModel['ai_summary_json'],
    };

    render(
      <EmailQuickView
        email={email}
        actionItemsRef={actionItemsRef}
        onReadFull={noop}
      />
    );

    expect(screen.getByText('Category:')).toBeInTheDocument();
    expect(screen.getByText('Informational')).toBeInTheDocument();
  });

  it('omits category entirely when ai_summary_json is absent', () => {
    render(
      <EmailQuickView
        email={baseEmail}
        actionItemsRef={actionItemsRef}
        onReadFull={noop}
      />
    );

    expect(screen.queryByText('Category:')).not.toBeInTheDocument();
  });
});
