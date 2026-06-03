/**
 * ReplyComposeModal — AI summary category rendering contract.
 *
 * Invariants:
 *   1. category present → category label + translated category rendered in reference block
 *   2. category absent  → category label not rendered, no placeholder
 *
 * Scope: reference context block only. Compose state and outbound body are not under test.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReplyComposeModal } from '../ReplyComposeModal';
import type { EmailViewModel } from '@types';

// ---------------------------------------------------------------------------
// react-i18next — deterministic English strings
// ---------------------------------------------------------------------------
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) => {
      const map: Record<string, string> = {
        'compose.reply': 'Reply',
        'compose.to_sender': `To: ${opts?.sender ?? ''}`,
        'compose.discard_draft': 'Discard draft',
        'compose.subject': 'Subject',
        'compose.cc': 'CC',
        'compose.cc_placeholder': 'CC',
        'compose.tools_title': 'Draft tools',
        'compose.tools_description': 'Adjust tone and apply templates.',
        'compose.tone': 'Tone',
        'compose.tone_professional': 'Professional',
        'compose.tone_casual': 'Casual',
        'compose.tone_concise': 'Concise',
        'compose.tone_empathetic': 'Empathetic',
        'compose.template': 'Template',
        'compose.select_template': 'Select template',
        'compose.no_templates_saved': 'No templates saved',
        'compose.loading_templates': 'Loading templates…',
        'compose.empty_templates_help': 'Save a reply as a template to reuse it.',
        'compose.apply_template': 'Apply template',
        'compose.save_as_template': 'Save as template',
        'compose.delete_template': 'Delete template',
        'compose.deleting': 'Deleting…',
        'compose.template_name': 'Template name',
        'compose.template_name_placeholder': 'My template',
        'compose.save': 'Save',
        'compose.saving': 'Saving…',
        'compose.reply_body': 'Reply',
        'compose.reply_body_help': 'Write your reply below.',
        'compose.reply_body_placeholder': 'Write your reply…',
        'compose.reference_not_sent': 'Reference — not sent',
        'compose.tone_value': `Tone: ${opts?.tone ?? ''}`,
        'compose.action_items': 'Action items',
        'compose.show_original': 'Show original',
        'compose.hide_original': 'Hide original',
        'compose.discard': 'Discard',
        'compose.send_reply': 'Send reply',
        'compose.sending': 'Sending…',
        'compose.attach': 'Attach',
        'compose.attachments_list': 'Attachments',
        'compose.remove_attachment': `Remove ${opts?.filename ?? ''}`,
        'compose.total_attachment_size': `Total: ${opts?.size ?? ''}`,
        'compose.attachment_privacy_notice': 'Attachments are sent securely.',
        'modal.urgency_label': 'Urgency:',
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
      return map[key] ?? key;
    },
    i18n: { language: 'en' },
  }),
}));

// ---------------------------------------------------------------------------
// framer-motion — render children without animation overhead
// ---------------------------------------------------------------------------
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...rest }: React.HTMLAttributes<HTMLDivElement>) =>
      React.createElement('div', rest, children),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
}));

// ---------------------------------------------------------------------------
// Child components not under test
// ---------------------------------------------------------------------------
vi.mock('../FocusTrap', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => React.createElement('div', null, children),
}));

vi.mock('../AiSummaryConfidence', () => ({
  default: () => null,
}));

vi.mock('../ThreadContextSignal', () => ({
  default: () => null,
}));

vi.mock('lucide-react', () => ({
  X: () => null,
  AlertCircle: () => null,
  RefreshCw: () => null,
  Mail: () => null,
  Sparkles: () => null,
  ChevronDown: () => null,
  Save: () => null,
  Trash2: () => null,
  Paperclip: () => null,
}));

// ---------------------------------------------------------------------------
// Utilities not under test
// ---------------------------------------------------------------------------
vi.mock('@utils/normalizeBodyText', () => ({
  normalizeBodyText: (s: string) => s,
}));

vi.mock('@utils/deriveThreadContext', () => ({
  deriveThreadContext: () => null,
}));

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const baseEmail: EmailViewModel = {
  account: 'test@example.com',
  subject: 'Re: Project Update',
  sender: 'sender@example.com',
  date: '2025-01-01',
  priority: 'Medium',
  category: 'Work',
  should_alert: false,
  summary: 'Test summary',
  action: 'None',
  gmail_message_id: 'msg-test-001',
  thread_id: 'thread-test-001',
};

const noop = () => {};
const replyTextareaRef = { current: null } as React.RefObject<HTMLTextAreaElement>;

const defaultProps = {
  email: baseEmail,
  replyBody: '',
  replySubject: 'Re: Project Update',
  replyCC: '',
  sending: false,
  panelError: null,
  replyTextareaRef,
  onDiscard: noop,
  onSend: noop,
  onReplyBodyChange: noop,
  onReplySubjectChange: noop,
  onReplyCCChange: noop,
  buildAttribution: (_date: string, sender: string) => `On some date, ${sender} wrote:`,
};

// ---------------------------------------------------------------------------

describe('ReplyComposeModal — AI summary category rendering in reference block', () => {
  it('renders category label and translated category when email.ai_summary_json.category is present', () => {
    const email: EmailViewModel = {
      ...baseEmail,
      ai_summary_text: 'This email requires action.',
      ai_summary_json: {
        overview: 'Requires action',
        action_items: ['Reply by Friday'],
        urgency: 'high',
        category: 'ACTION_REQUIRED',
      },
    };

    render(<ReplyComposeModal {...defaultProps} email={email} />);

    expect(screen.getByText('Category:')).toBeInTheDocument();
    expect(screen.getByText('Action Required')).toBeInTheDocument();
  });

  it('omits category label when email.ai_summary_json.category is absent', () => {
    const email: EmailViewModel = {
      ...baseEmail,
      ai_summary_text: 'Summary without category.',
      ai_summary_json: {
        overview: 'No category',
        action_items: [],
        urgency: 'medium',
      },
    };

    render(<ReplyComposeModal {...defaultProps} email={email} />);

    expect(screen.queryByText('Category:')).not.toBeInTheDocument();
  });

  it('omits category entirely when ai_summary_json is absent', () => {
    render(<ReplyComposeModal {...defaultProps} email={baseEmail} />);

    expect(screen.queryByText('Category:')).not.toBeInTheDocument();
  });

  it('renders category without urgency when only category is present', () => {
    const email: EmailViewModel = {
      ...baseEmail,
      ai_summary_text: 'Project update notes.',
      // Cast omits urgency to simulate partial/legacy runtime data where
      // the field is missing; proves category renders without urgency present.
      ai_summary_json: {
        overview: 'Project update',
        action_items: [],
        category: 'PROJECT_WORK',
      } as unknown as EmailViewModel['ai_summary_json'],
    };

    render(<ReplyComposeModal {...defaultProps} email={email} />);

    expect(screen.getByText('Category:')).toBeInTheDocument();
    expect(screen.getByText('Informational')).toBeInTheDocument();
  });
});
