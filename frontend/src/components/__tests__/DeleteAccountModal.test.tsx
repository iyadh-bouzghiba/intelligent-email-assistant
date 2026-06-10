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

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const MOCK_ACCOUNTS = [
  {
    account_id: 'user1@gmail.com',
    connected: true,
    auth_required: false,
  },
  {
    account_id: 'user2@gmail.com',
    connected: true,
    auth_required: true,
  },
];

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  onSuccess: vi.fn(),
  isDisconnecting: false,
  connectedAccounts: MOCK_ACCOUNTS,
  onDeleteAllData: vi.fn(),
};

const renderModal = (
  props: Partial<React.ComponentProps<typeof DeleteAccountModal>> = {}
) => render(
  React.createElement(DeleteAccountModal, {
    ...defaultProps,
    ...props,
  })
);

const selectFirstAccountAndContinue = () => {
  fireEvent.click(
    screen.getByRole('radio', { name: /user1@gmail\.com/ })
  );
  fireEvent.click(
    screen.getByRole('button', { name: 'delete_modal.btn_continue' })
  );
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DeleteAccountModal', () => {
  it('renders nothing when closed', () => {
    renderModal({ isOpen: false });

    expect(
      screen.queryByText('delete_modal.title')
    ).toBeNull();
  });

  it('renders account selection step 1 when open', () => {
    renderModal();

    expect(
      screen.getByText('delete_modal.title')
    ).toBeDefined();
    expect(
      screen.getByText('delete_modal.subtitle_select')
    ).toBeDefined();
    expect(
      screen.getByText('delete_modal.select_account_label')
    ).toBeDefined();
  });

  it('displays both connected account ids in step 1', () => {
    renderModal();

    expect(
      screen.getByText('user1@gmail.com')
    ).toBeDefined();
    expect(
      screen.getByText('user2@gmail.com')
    ).toBeDefined();
  });

  it('shows reconnect chip for auth_required account', () => {
    renderModal();

    expect(
      screen.getByText('Reconnect required')
    ).toBeDefined();
  });

  it('continue button disabled until account selected', () => {
    renderModal();

    const continueButton = screen.getByRole('button', {
      name: 'delete_modal.btn_continue',
    });

    expect(continueButton).toBeDisabled();

    fireEvent.click(
      screen.getByRole('radio', { name: /user1@gmail\.com/ })
    );

    expect(continueButton).toBeEnabled();
  });

  it('continue button enabled after account selected', () => {
    renderModal();

    fireEvent.click(
      screen.getByRole('radio', { name: /user1@gmail\.com/ })
    );

    expect(
      screen.getByRole('button', {
        name: 'delete_modal.btn_continue',
      })
    ).toBeEnabled();
  });

  it('advances to step 2 showing selected account id', () => {
    renderModal();

    selectFirstAccountAndContinue();

    expect(
      screen.getByText('delete_modal.subtitle_confirm')
    ).toBeDefined();
    expect(
      screen.getByText('delete_modal.selected_account_label')
    ).toBeDefined();
    expect(
      screen.getByText('user1@gmail.com')
    ).toBeDefined();
  });

  it('confirm button disabled until exact phrase typed', () => {
    renderModal();

    selectFirstAccountAndContinue();

    const confirmButton = screen.getByRole('button', {
      name: 'delete_modal.btn_confirm',
    });

    expect(confirmButton).toBeDisabled();

    fireEvent.change(
      screen.getByPlaceholderText('DISCONNECT ACCOUNT'),
      { target: { value: 'DISCONNECT' } }
    );

    expect(confirmButton).toBeDisabled();
  });

  it('confirm button enabled with exact phrase', () => {
    renderModal();

    selectFirstAccountAndContinue();

    fireEvent.change(
      screen.getByPlaceholderText('DISCONNECT ACCOUNT'),
      { target: { value: 'DISCONNECT ACCOUNT' } }
    );

    expect(
      screen.getByRole('button', {
        name: 'delete_modal.btn_confirm',
      })
    ).toBeEnabled();
  });

  it('calls onSuccess with selected account id', () => {
    const onSuccess = vi.fn();

    renderModal({ onSuccess });

    selectFirstAccountAndContinue();

    fireEvent.change(
      screen.getByPlaceholderText('DISCONNECT ACCOUNT'),
      { target: { value: 'DISCONNECT ACCOUNT' } }
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'delete_modal.btn_confirm',
      })
    );

    expect(onSuccess).toHaveBeenCalledWith(
      'user1@gmail.com'
    );
  });

  it('displays error when error prop provided', () => {
    renderModal({
      error: 'Disconnect failed. Please try again.',
    });

    expect(
      screen.getByText('Disconnect failed. Please try again.')
    ).toBeDefined();
  });

  it('calls onDeleteAllData when delete all link clicked', () => {
    const onDeleteAllData = vi.fn();

    renderModal({ onDeleteAllData });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'delete_modal.delete_all_link',
      })
    );

    expect(onDeleteAllData).toHaveBeenCalledTimes(1);
  });
});