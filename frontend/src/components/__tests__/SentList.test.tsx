import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SentList } from '../SentList';
import type { SentEmail } from '@types';

vi.mock('react-i18next', () => {
  const stableT = (k: string, opts?: Record<string, string>) => {
    const templates: Record<string, string> = {
      'sent.open_email_label': 'Open email to {{recipient}}: {{subject}}',
    };
    const base = templates[k] ?? k;
    if (!opts) return base;
    return Object.entries(opts).reduce(
      (s, [k2, v]) => s.replace('{{' + k2 + '}}', v),
      base
    );
  };

  return {
    useTranslation: () => ({
      t: stableT,
      i18n: {
        resolvedLanguage: 'en',
        language: 'en',
      },
    }),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

const mockEmail: SentEmail = {
  id: 'test-id-1',
  account_id: 'test@gmail.com',
  gmail_message_id: 'abc123',
  thread_id: 'thread-1',
  to_address: 'recipient@example.com',
  cc_addresses: null,
  subject: 'Meeting tomorrow',
  body_preview:
    'Let us meet at 10am.\n\nOn May 1, 2026, at 9am, Someone wrote:\nOriginal message here',
  sent_at: '2026-06-13T10:00:00Z',
  has_attachments: false,
};

describe('SentList', () => {
  it('renders loading skeleton when loading=true', () => {
    render(<SentList emails={[]} loading={true} onSelect={vi.fn()} />);

    expect(screen.getByLabelText('sent.loading')).toBeTruthy();
  });

  it('renders empty state when emails empty and not loading', () => {
    render(<SentList emails={[]} loading={false} onSelect={vi.fn()} />);

    expect(screen.getByText('sent.empty_title')).toBeTruthy();
    expect(screen.getByText('sent.empty_description')).toBeTruthy();
    expect(screen.getByText('sent.empty_scope_notice')).toBeTruthy();
  });

  it('renders sent email card with subject', () => {
    render(<SentList emails={[mockEmail]} loading={false} onSelect={vi.fn()} />);

    expect(screen.getByText('Meeting tomorrow')).toBeTruthy();
  });

  it('renders sent email card with recipient', () => {
    render(<SentList emails={[mockEmail]} loading={false} onSelect={vi.fn()} />);

    expect(screen.getByText(/recipient@example\.com/)).toBeTruthy();
  });

  it('card aria-label includes recipient and subject', () => {
    render(<SentList emails={[mockEmail]} loading={false} onSelect={vi.fn()} />);

    const btn = screen.getByRole('button', {
      name: /recipient@example\.com.*Meeting tomorrow|Meeting tomorrow.*recipient@example\.com/,
    });

    expect(btn).toBeTruthy();
  });

  it('body preview strips quoted thread content', () => {
    render(<SentList emails={[mockEmail]} loading={false} onSelect={vi.fn()} />);

    expect(screen.queryByText(/On May 1, 2026/)).toBeNull();
    expect(screen.getByText(/Let us meet at 10am/)).toBeTruthy();
  });

  it('body preview preserves normal non-quoted content', () => {
    const normalPreview: SentEmail = {
      ...mockEmail,
      id: 'test-id-normal-preview',
      body_preview: 'Plain sent preview without a quoted reply marker.',
    };

    render(<SentList emails={[normalPreview]} loading={false} onSelect={vi.fn()} />);

    expect(screen.getByText(/Plain sent preview without a quoted reply marker/)).toBeTruthy();
  });

  it('calls onSelect when card is clicked', () => {
    const onSelect = vi.fn();

    render(<SentList emails={[mockEmail]} loading={false} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: /Meeting tomorrow/ }));

    expect(onSelect).toHaveBeenCalledWith(mockEmail);
  });

  it('shows attachment indicator when has_attachments=true', () => {
    const withAttachment: SentEmail = { ...mockEmail, has_attachments: true };

    render(<SentList emails={[withAttachment]} loading={false} onSelect={vi.fn()} />);

    expect(screen.getByLabelText('inbox.has_attachments')).toBeTruthy();
  });
});