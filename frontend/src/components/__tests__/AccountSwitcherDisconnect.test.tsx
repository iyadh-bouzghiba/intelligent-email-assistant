import React, { useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AccountSwitcherList } from '../AccountSwitcherList';
import { apiService } from '@services';

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

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts?.account ? `${key}:${opts.account}` : key,
    i18n: { resolvedLanguage: 'en', language: 'en' },
  }),
}));

vi.mock('@services', () => ({
  apiService: {
    disconnectAccount: vi.fn().mockResolvedValue({ status: 'ok', account_id: 'test@example.com' }),
  },
}));

const TEST_ACCOUNT = 'test@example.com';

const CONNECTED_ACCOUNTS = [
  { account_id: TEST_ACCOUNT, connected: true, auth_required: false },
];

/**
 * Minimal host for the live production disconnect path:
 * AccountSwitcherList → onRequestDisconnect → setConfirmDisconnect →
 * inline confirmDisconnect modal (matching App.tsx) → handleDisconnect.
 */
function DisconnectHost() {
  const [confirmDisconnect, setConfirmDisconnect] = useState<string | null>(null);

  const handleDisconnect = async (accountId: string) => {
    setConfirmDisconnect(null);
    await apiService.disconnectAccount(accountId);
  };

  return (
    <>
      <AccountSwitcherList
        connectedAccounts={CONNECTED_ACCOUNTS}
        activeEmail={null}
        offlineAccounts={new Set()}
        showMaxAccountsMsg={false}
        maxAccounts={3}
        authUrl="/auth/google"
        onSwitchAccount={() => {}}
        onRequestDisconnect={(id) => setConfirmDisconnect(id)}
        onMaxAccountsAttempt={() => {}}
        onClose={() => {}}
        aiLanguage="en"
        aiLanguageLoading={false}
        aiLanguageSaving={false}
        aiLanguageError={null}
        aiLanguageSavedAccountId={null}
        languageOptions={[]}
        onAiLanguageChange={() => {}}
        languageAriaIdPrefix="desktop"
      />

      {confirmDisconnect && (
        <div data-testid="confirm-disconnect-modal">
          <h3>auth.disconnect_account_heading</h3>
          <p>{`auth.disconnect_account_prompt:${confirmDisconnect}`}</p>
          <p>auth.disconnect_account_notice</p>
          <div>
            <button onClick={() => setConfirmDisconnect(null)}>
              common.cancel
            </button>
            <button onClick={() => handleDisconnect(confirmDisconnect)}>
              auth.disconnect_account_confirm
            </button>
          </div>
        </div>
      )}
    </>
  );
}

const renderHost = () => render(React.createElement(DisconnectHost));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiService.disconnectAccount).mockResolvedValue({ status: 'ok', account_id: TEST_ACCOUNT });
});

describe('AccountSwitcherDisconnect', () => {
  it('disconnect icon opens confirm modal', () => {
    renderHost();

    fireEvent.click(
      screen.getByTitle(`settings.disconnect_account_title:${TEST_ACCOUNT}`)
    );

    expect(screen.getByTestId('confirm-disconnect-modal')).toBeDefined();
  });

  it('confirm modal shows account id', () => {
    renderHost();

    fireEvent.click(
      screen.getByTitle(`settings.disconnect_account_title:${TEST_ACCOUNT}`)
    );

    expect(
      screen.getByText(`auth.disconnect_account_prompt:${TEST_ACCOUNT}`)
    ).toBeDefined();
  });

  it('confirm modal cancel closes modal', () => {
    renderHost();

    fireEvent.click(
      screen.getByTitle(`settings.disconnect_account_title:${TEST_ACCOUNT}`)
    );

    fireEvent.click(screen.getByText('common.cancel'));

    expect(screen.queryByTestId('confirm-disconnect-modal')).toBeNull();
  });

  it('confirm modal shows disconnect consequences copy', () => {
    renderHost();

    fireEvent.click(
      screen.getByTitle(`settings.disconnect_account_title:${TEST_ACCOUNT}`)
    );

    expect(screen.getByText('auth.disconnect_account_notice')).toBeDefined();
  });

  it('confirm modal disconnect button calls handleDisconnect', async () => {
    renderHost();

    fireEvent.click(
      screen.getByTitle(`settings.disconnect_account_title:${TEST_ACCOUNT}`)
    );

    fireEvent.click(screen.getByText('auth.disconnect_account_confirm'));

    await waitFor(() => {
      expect(vi.mocked(apiService.disconnectAccount)).toHaveBeenCalledWith(TEST_ACCOUNT);
    });
  });

  it('confirm modal not visible when no confirmDisconnect state', () => {
    renderHost();

    expect(screen.queryByTestId('confirm-disconnect-modal')).toBeNull();
  });
});
