import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ThreadSpine } from '../ThreadSpine';
import type { SpineSignalResult } from '@utils/deriveSpineSignals';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (key === 'spine.thread_context') return 'Thread context';
      if (key === 'spine.urgency_high') return 'Verify — Financial';
      if (key === 'spine.urgency_medium') return 'Needs Review';
      if (key === 'spine.has_attachments') return 'Has attachments';
      if (key === 'spine.recency_today') return 'Active today';
      if (key === 'spine.recency_days') return `${opts?.count} days ago`;
      if (key === 'spine.reply_pending') return `${opts?.count}d — reply pending`;
      if (key === 'spine.thread_depth') return `${opts?.count} messages`;
      return key;
    },
  }),
}));

vi.mock('lucide-react', () => ({
  Paperclip: () => null,
  Clock: () => null,
}));

const defaults: SpineSignalResult = {
  urgencyLevel: 'none',
  hasAttachments: null,
  daysSinceLastActivity: null,
  isPendingReply: null,
  threadDepth: null,
  hasAnySignal: false,
};

const makeResult = (overrides: Partial<SpineSignalResult> = {}): SpineSignalResult => ({
  ...defaults,
  ...overrides,
});

describe('ThreadSpine', () => {
  it('returns null when hasAnySignal=false', () => {
    const { container } = render(<ThreadSpine result={makeResult()} />);
    expect(screen.queryByRole('group', { name: 'Thread context' })).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });

  it('renders urgency chip and correct container attributes when urgencyLevel="high"', () => {
    render(<ThreadSpine result={makeResult({ urgencyLevel: 'high', hasAnySignal: true })} />);
    const group = screen.getByRole('group', { name: 'Thread context' });
    expect(group).toBeInTheDocument();
    expect(group).toHaveAttribute('dir', 'auto');
    const chip = screen.getByRole('img', { name: 'Verify — Financial' });
    expect(chip).toHaveAttribute('title', 'Verify — Financial');
  });

  it('renders exactly 4 chips when all visible signals are present', () => {
    render(
      <ThreadSpine
        result={makeResult({
          urgencyLevel: 'medium',
          hasAttachments: true,
          daysSinceLastActivity: 3,
          isPendingReply: true,
          threadDepth: 7,
          hasAnySignal: true,
        })}
      />,
    );
    const chips = screen.getAllByRole('img');
    expect(chips).toHaveLength(4);
    expect(chips[0]).toHaveAttribute('aria-label', 'Needs Review');
    expect(chips[1]).toHaveAttribute('aria-label', 'Has attachments');
    expect(chips[2]).toHaveAttribute('aria-label', '3d — reply pending');
    expect(chips[3]).toHaveAttribute('aria-label', '7 messages');
  });

  it('recency chip uses pending label when isPendingReply=true', () => {
    render(
      <ThreadSpine
        result={makeResult({
          daysSinceLastActivity: 2,
          isPendingReply: true,
          hasAnySignal: true,
        })}
      />,
    );
    expect(screen.getByRole('img', { name: '2d — reply pending' })).toBeInTheDocument();
    expect(screen.queryByText('2 days ago')).not.toBeInTheDocument();
  });

  it('attachment chip renders only when hasAttachments=true', () => {
    const { rerender } = render(
      <ThreadSpine result={makeResult({ hasAttachments: true, hasAnySignal: true })} />,
    );
    expect(screen.getByRole('img', { name: 'Has attachments' })).toBeInTheDocument();

    rerender(
      <ThreadSpine result={makeResult({ hasAttachments: false, hasAnySignal: false })} />,
    );
    expect(screen.queryByRole('img', { name: 'Has attachments' })).not.toBeInTheDocument();
  });
});
