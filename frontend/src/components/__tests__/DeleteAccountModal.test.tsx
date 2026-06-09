import React from 'react';
import { render, screen, fireEvent } from
  '@testing-library/react';
import { describe, it, expect, vi, beforeEach }
  from 'vitest';
import DeleteAccountModal from
  '../DeleteAccountModal';

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.ComponentPropsWithoutRef<'div'>) =>
      React.createElement('div', props, children),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
}));

vi.mock('../FocusTrap', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
}));

const MOCK_ACCOUNTS = [
  { account_id: 'user1@gmail.com' },
  { account_id: 'user2@gmail.com' },
];

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  onSuccess: vi.fn(),
  isDeleting: false,
  connectedAccounts: MOCK_ACCOUNTS,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DeleteAccountModal', () => {
  it('renders nothing when closed', () => {
    render(
      React.createElement(DeleteAccountModal, {
        ...defaultProps, isOpen: false
      })
    );
    expect(
      screen.queryByText('Delete Account')
    ).toBeNull();
  });

  it('renders step 1 warning when open', () => {
    render(
      React.createElement(DeleteAccountModal,
        defaultProps)
    );
    expect(
      screen.getByText('THIS ACTION IS IRREVERSIBLE',
        { exact: false })
    ).toBeDefined();
  });

  it('displays connected account ids in step 1', () => {
    render(
      React.createElement(DeleteAccountModal,
        defaultProps)
    );
    expect(
      screen.getByText('user1@gmail.com')
    ).toBeDefined();
    expect(
      screen.getByText('user2@gmail.com')
    ).toBeDefined();
  });

  it('advances to step 2 on Continue click', () => {
    render(
      React.createElement(DeleteAccountModal,
        defaultProps)
    );
    fireEvent.click(screen.getByText('Continue'));
    expect(
      screen.getByPlaceholderText('DELETE MY ACCOUNT')
    ).toBeDefined();
  });

  it('confirm button disabled until exact phrase', () => {
    render(
      React.createElement(DeleteAccountModal,
        defaultProps)
    );
    fireEvent.click(screen.getByText('Continue'));
    const btn = screen.getByText('Delete My Account')
      .closest('button');
    expect(btn).toBeDefined();
    expect((btn as HTMLButtonElement).disabled)
      .toBe(true);
    fireEvent.change(
      screen.getByPlaceholderText('DELETE MY ACCOUNT'),
      { target: { value: 'DELETE MY' } }
    );
    expect((btn as HTMLButtonElement).disabled)
      .toBe(true);
  });

  it('confirm button enabled with exact phrase', () => {
    render(
      React.createElement(DeleteAccountModal,
        defaultProps)
    );
    fireEvent.click(screen.getByText('Continue'));
    fireEvent.change(
      screen.getByPlaceholderText('DELETE MY ACCOUNT'),
      { target: { value: 'DELETE MY ACCOUNT' } }
    );
    const btn = screen.getByText('Delete My Account')
      .closest('button');
    expect((btn as HTMLButtonElement).disabled)
      .toBe(false);
  });

  it('calls onSuccess with exact phrase confirmed', () => {
    const onSuccess = vi.fn();
    render(
      React.createElement(DeleteAccountModal, {
        ...defaultProps, onSuccess
      })
    );
    fireEvent.click(screen.getByText('Continue'));
    fireEvent.change(
      screen.getByPlaceholderText('DELETE MY ACCOUNT'),
      { target: { value: 'DELETE MY ACCOUNT' } }
    );
    fireEvent.click(
      screen.getByText('Delete My Account')
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('displays error message when error prop set', () => {
    render(
      React.createElement(DeleteAccountModal, {
        ...defaultProps,
        error: 'Deletion failed. Please try again.'
      })
    );
    expect(
      screen.getByText(
        'Deletion failed. Please try again.')
    ).toBeDefined();
  });
});
