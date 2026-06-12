import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DeleteAllDataModal from '../DeleteAllDataModal';

vi.mock('framer-motion', () => ({
  motion: {
    div: ({
      children,
      initial: _initial,
      animate: _animate,
      exit: _exit,
      transition: _transition,
      ...props
    }: React.ComponentPropsWithoutRef<'div'> & {
      initial?: unknown;
      animate?: unknown;
      exit?: unknown;
      transition?: unknown;
    }) => React.createElement('div', props, children),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
}));

vi.mock('../FocusTrap', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const onClose = vi.fn();
const onSuccess = vi.fn();

const defaultProps = {
  isOpen: true,
  onClose,
  onSuccess,
  isDeleting: false,
};

const renderModal = (
  props: Partial<React.ComponentProps<typeof DeleteAllDataModal>> = {}
) => render(
  React.createElement(DeleteAllDataModal, {
    ...defaultProps,
    ...props,
  })
);

beforeEach(() => {
  vi.clearAllMocks();
  document.body.classList.remove('panel-open');
});

describe('DeleteAllDataModal', () => {
  it('renders nothing when closed', () => {
    const { container } = renderModal({ isOpen: false });

    expect(container.firstChild).toBeNull();
  });

  it('renders will-be-deleted items', () => {
    renderModal();

    expect(
      screen.getByText('delete_all_modal.item_emails')
    ).toBeDefined();
    expect(
      screen.getByText('delete_all_modal.item_templates')
    ).toBeDefined();
    expect(
      screen.getByText('delete_all_modal.item_preferences')
    ).toBeDefined();
    expect(
      screen.getByText('delete_all_modal.item_accounts')
    ).toBeDefined();
  });

  it('renders will-not-be-deleted gmail-safe items', () => {
    renderModal();

    expect(
      screen.getByText('delete_all_modal.item_gmail')
    ).toBeDefined();
    expect(
      screen.getByText('delete_all_modal.item_google')
    ).toBeDefined();
  });

  it('confirm button disabled when phrase empty', () => {
    renderModal();

    expect(
      screen.getByRole('button', {
        name: 'delete_all_modal.btn_confirm',
      })
    ).toBeDisabled();
  });

  it('confirm button disabled with partial phrase', () => {
    renderModal();

    fireEvent.change(
      screen.getByLabelText('delete_all_modal.confirm_instruction'),
      { target: { value: 'DELETE MY' } }
    );

    expect(
      screen.getByRole('button', {
        name: 'delete_all_modal.btn_confirm',
      })
    ).toBeDisabled();
  });

  it('confirm button enabled with exact DELETE MY ACCOUNT', () => {
    renderModal();

    fireEvent.change(
      screen.getByLabelText('delete_all_modal.confirm_instruction'),
      { target: { value: 'DELETE MY ACCOUNT' } }
    );

    expect(
      screen.getByRole('button', {
        name: 'delete_all_modal.btn_confirm',
      })
    ).toBeEnabled();
  });

  it('calls onSuccess on confirm with exact phrase', () => {
    renderModal();

    fireEvent.change(
      screen.getByLabelText('delete_all_modal.confirm_instruction'),
      { target: { value: 'DELETE MY ACCOUNT' } }
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'delete_all_modal.btn_confirm',
      })
    );

    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('renders error prop when provided', () => {
    renderModal({
      error: 'test error',
    });

    expect(
      screen.getByText('test error')
    ).toBeDefined();
  });
});
