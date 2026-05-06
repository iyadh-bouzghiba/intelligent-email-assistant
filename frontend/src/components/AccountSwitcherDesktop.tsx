import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { AccountInfo } from '@types';
import { AccountSwitcherList, type AccountSwitcherLanguageProps } from './AccountSwitcherList';
import { getAccountColor, getEmailInitials } from './accountSwitcherHelpers';

interface Props extends AccountSwitcherLanguageProps {
  connectedAccounts: AccountInfo[];
  activeEmail: string | null;
  offlineAccounts: Set<string>;
  maxAccounts: number;
  authUrl: string;
  onSwitchAccount: (accountId: string) => Promise<void>;
  onRequestDisconnect: (accountId: string) => void;
}

/**
 * Desktop-only account switcher (hidden below sm).
 *
 * Trigger: full button with avatar + username label + chevron (matches prior design).
 * Panel:   anchored popover dropdown, right-aligned to the trigger.
 *
 * Outside-click detection lives here — not in App.tsx — since only the desktop surface
 * needs it (mobile uses a full-scrim backdrop instead).
 *
 * State is entirely self-contained.
 */
export function AccountSwitcherDesktop({
  connectedAccounts,
  activeEmail,
  offlineAccounts,
  maxAccounts,
  authUrl,
  onSwitchAccount,
  onRequestDisconnect,
  aiLanguage,
  aiLanguageLoading,
  aiLanguageSaving,
  aiLanguageError,
  aiLanguageSavedAccountId,
  languageOptions,
  onAiLanguageChange,
  languageAriaIdPrefix,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [showMaxMsg, setShowMaxMsg] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Outside-click detection: close dropdown when click lands outside both button and menu.
  // Clears the max-accounts message when closed.
  useEffect(() => {
    if (!isOpen) {
      setShowMaxMsg(false);
      return;
    }
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (menuRef.current?.contains(target)) return;
      if (buttonRef.current?.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener('mousedown', onMouseDown, true);
    return () => document.removeEventListener('mousedown', onMouseDown, true);
  }, [isOpen]);

  const isOffline = activeEmail ? offlineAccounts.has(activeEmail) : false;
  const close = () => setIsOpen(false);

  return (
    <div className="hidden sm:block relative">
      {/* Full trigger: avatar + username + chevron */}
      <button
        ref={buttonRef}
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen((v) => !v);
        }}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-controls="account-switcher-desktop-popover"
        className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-slate-200 hover:bg-white/[0.05] transition-all min-w-0"
      >
        {activeEmail ? (
          <>
            <span
              className={`relative inline-flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br ${getAccountColor(activeEmail)} text-[10px] font-black text-white flex-shrink-0 shadow-lg ring-2 ring-primary-500/35`}
            >
              {getEmailInitials(activeEmail)}
              <span
                className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-brand-surface ${isOffline ? 'bg-[#EF4444]' : 'bg-[#22C55E]'}`}
              />
            </span>
            <span className="text-[11px] font-bold text-slate-300 truncate max-w-[120px]">
              {activeEmail.split('@')[0]}
            </span>
          </>
        ) : (
          <>
            <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-800 text-[10px] font-black text-slate-400 flex-shrink-0 shadow-lg">
              ?
            </span>
            <span className="text-[11px] font-bold text-slate-500 truncate">
              Select Account
            </span>
          </>
        )}
        <ChevronRight
          size={11}
          className={`transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}
        />
      </button>

      {/* Anchored dropdown */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            id="account-switcher-desktop-popover"
            ref={menuRef}
            onMouseDown={(e) => e.stopPropagation()}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="absolute right-0 top-full mt-2 w-64 rounded-2xl bg-brand-surface border border-brand-border shadow-2xl z-[100] overflow-hidden max-h-[70vh] overflow-y-auto custom-scrollbar"
          >
            <AccountSwitcherList
              connectedAccounts={connectedAccounts}
              activeEmail={activeEmail}
              offlineAccounts={offlineAccounts}
              showMaxAccountsMsg={showMaxMsg}
              maxAccounts={maxAccounts}
              authUrl={authUrl}
              onSwitchAccount={async (id) => {
                close();
                await onSwitchAccount(id);
              }}
              onRequestDisconnect={(id) => {
                close();
                onRequestDisconnect(id);
              }}
              onMaxAccountsAttempt={() => setShowMaxMsg(true)}
              onClose={close}
              aiLanguage={aiLanguage}
              aiLanguageLoading={aiLanguageLoading}
              aiLanguageSaving={aiLanguageSaving}
              aiLanguageError={aiLanguageError}
              aiLanguageSavedAccountId={aiLanguageSavedAccountId}
              languageOptions={languageOptions}
              onAiLanguageChange={onAiLanguageChange}
              languageAriaIdPrefix={languageAriaIdPrefix}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
