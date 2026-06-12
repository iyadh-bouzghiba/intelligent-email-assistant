import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsPanel from '../SettingsPanel';

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
    i18n: {
      resolvedLanguage: 'en',
      language: 'en',
    },
  }),
}));

const onClose = vi.fn();
const onDeleteAllData = vi.fn();

const defaultProps = {
  isOpen: true,
  onClose,
  onDeleteAllData,
};

const renderPanel = (
  props: Partial<React.ComponentProps<typeof SettingsPanel>> = {}
) => render(
  React.createElement(SettingsPanel, {
    ...defaultProps,
    ...props,
  })
);

beforeEach(() => {
  vi.clearAllMocks();
  document.body.classList.remove('panel-open');
});

describe('SettingsPanel', () => {
  it('renders nothing when closed', () => {
    const { container } = renderPanel({ isOpen: false });

    expect(container.firstChild).toBeNull();
  });

  it('renders settings title when open', () => {
    renderPanel();

    expect(
      screen.getByText('settings_panel.title')
    ).toBeDefined();
  });

  it('renders danger zone section', () => {
    renderPanel();

    expect(
      screen.getByText('settings_panel.danger_zone_title')
    ).toBeDefined();
    expect(
      screen.getByText('settings_panel.danger_zone_subtitle')
    ).toBeDefined();
  });

  it('delete all button calls onDeleteAllData', () => {
    renderPanel();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'settings_panel.delete_all_btn',
      })
    );

    expect(onDeleteAllData).toHaveBeenCalledTimes(1);
  });

  it('close button calls onClose', () => {
    renderPanel();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.close',
      })
    );

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('adds panel-open class to body when open', () => {
    const { unmount } = renderPanel({ isOpen: true });

    expect(
      document.body.classList.contains('panel-open')
    ).toBe(true);

    unmount();

    expect(
      document.body.classList.contains('panel-open')
    ).toBe(false);
  });
});
