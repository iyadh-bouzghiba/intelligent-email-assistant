import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ThreadContextSignal from '../ThreadContextSignal';
import type { ThreadContextResult } from '@utils/deriveThreadContext';

// ─────────────────────────────────────────────────────────────
// react-i18next — deterministic English strings, no i18n init
// ─────────────────────────────────────────────────────────────
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'compose.context.strip_aria_label': 'Thread context signals',
        'compose.context.urgency_high': 'Verify — Financial',
        'compose.context.urgency_high_aria': 'Low-confidence AI summary for a financial thread. Verify before acting.',
        'compose.context.urgency_medium': 'Needs Review',
        'compose.context.urgency_medium_aria': 'Low-confidence AI summary. Review before acting.',
        'compose.context.has_attachments': 'Thread has attachments',
        'compose.context.has_attachments_aria': 'This thread has attachments',
        'compose.context.thread_depth': `${opts?.count} messages in this thread`,
        'compose.context.thread_depth_aria': `This thread has ${opts?.count} messages`,
      };
      return map[key] ?? key;
    },
  }),
}));

// ─────────────────────────────────────────────────────────────
// lucide-react — stub Paperclip so SVG does not interfere
// ─────────────────────────────────────────────────────────────
vi.mock('lucide-react', () => ({
  Paperclip: () => null,
}));

// ─────────────────────────────────────────────────────────────
// Fixtures
// ─────────────────────────────────────────────────────────────
const noSignals: ThreadContextResult = {
  threadDepth: 1,
  threadHasAttachments: null,
  urgencyLevel: 'none',
  daysSinceLastMessage: null,
  lastSenderIsCorrespondent: null,
  hasPendingReply: null,
};

const allSignals: ThreadContextResult = {
  threadDepth: 5,
  threadHasAttachments: true,
  urgencyLevel: 'high',
  daysSinceLastMessage: null,
  lastSenderIsCorrespondent: null,
  hasPendingReply: null,
};

// ─────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────
describe('ThreadContextSignal', () => {
  it('renders nothing when no live V1 signal is active', () => {
    const { container } = render(<ThreadContextSignal result={noSignals} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the urgency high chip', () => {
    render(<ThreadContextSignal result={{ ...noSignals, urgencyLevel: 'high' }} />);
    expect(screen.getByText('Verify — Financial')).toBeInTheDocument();
  });

  it('renders the urgency medium chip', () => {
    render(<ThreadContextSignal result={{ ...noSignals, urgencyLevel: 'medium' }} />);
    expect(screen.getByText('Needs Review')).toBeInTheDocument();
  });

  it('renders the attachment chip when threadHasAttachments === true', () => {
    render(<ThreadContextSignal result={{ ...noSignals, threadHasAttachments: true }} />);
    expect(screen.getByText('Thread has attachments')).toBeInTheDocument();
  });

  it('renders the depth chip when threadDepth >= 3', () => {
    render(<ThreadContextSignal result={{ ...noSignals, threadDepth: 4, urgencyLevel: 'none' }} />);
    expect(screen.getByText('4 messages in this thread')).toBeInTheDocument();
  });

  it('hides the depth chip when threadDepth is 2', () => {
    render(<ThreadContextSignal result={{ ...noSignals, threadDepth: 2, urgencyLevel: 'none' }} />);
    expect(screen.queryByText(/messages in this thread/)).not.toBeInTheDocument();
  });

  it('hides the depth chip when threadDepth is 1', () => {
    render(<ThreadContextSignal result={{ ...noSignals, urgencyLevel: 'none' }} />);
    expect(screen.queryByText(/messages in this thread/)).not.toBeInTheDocument();
  });

  it('renders all signals in order: urgency → attachments → depth', () => {
    render(<ThreadContextSignal result={allSignals} />);
    const group = screen.getByRole('group');
    const chips = Array.from(group.children) as HTMLElement[];
    expect(chips).toHaveLength(3);
    expect(chips[0]).toHaveAttribute('aria-label', 'Low-confidence AI summary for a financial thread. Verify before acting.');
    expect(chips[1]).toHaveAttribute('aria-label', 'This thread has attachments');
    expect(chips[2]).toHaveAttribute('aria-label', 'This thread has 5 messages');
  });

  it('deferred fields do not produce visible output', () => {
    const withDeferredNull: ThreadContextResult = {
      ...noSignals,
      daysSinceLastMessage: null,
      lastSenderIsCorrespondent: null,
      hasPendingReply: null,
    };
    const { container } = render(<ThreadContextSignal result={withDeferredNull} />);
    expect(container.firstChild).toBeNull();
  });
});
