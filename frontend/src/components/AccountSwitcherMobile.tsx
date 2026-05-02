import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, User } from 'lucide-react';
import { AccountInfo } from '@types';
import { AccountSwitcherList } from './AccountSwitcherList';
import { getAccountColor, getEmailInitials } from './accountSwitcherHelpers';

interface Props {
  connectedAccounts: AccountInfo[];
  activeEmail: string | null;
  offlineAccounts: Set<string>;
  maxAccounts: number;
  authUrl: string;
  onSwitchAccount: (accountId: string) => Promise<void>;
  onRequestDisconnect: (accountId: string) => void;
}

/**
 * Mobile-only account switcher (hidden on sm+).
 *
 * Trigger: compact pill button — avatar + truncated username + chevron.
 *          Visually matches the header chrome (same bg/border as desktop trigger).
 * Panel:   small anchored popover below the trigger, right-aligned.
 *          NOT a full-width bottom-sheet — appropriate for a max-3-account surface.
 *
 * Outside-tap close uses a document-level `pointerdown` capture listener, which
 * fires immediately on touch without the ~300ms simulated-mouse delay.
 *
 * State is entirely self-contained — open/close and max-accounts message
 * are owned here, not in App.tsx.
 */
export function AccountSwitcherMobile({
  connectedAccounts,
  activeEmail,
  offlineAccounts,
  maxAccounts,
  authUrl,
  onSwitchAccount,
  onRequestDisconnect,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [showMaxMsg, setShowMaxMsg] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Outside-tap detection via pointerdown capture — fires promptly on touch
  // without the simulated-mouse 300ms delay. Clears showMaxMsg on close.
  // Same pattern as AccountSwitcherDesktop's mousedown handler.
  useEffect(() => {
    if (!isOpen) {
      setShowMaxMsg(false);
      return;
    }
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (popoverRef.current?.contains(target)) return;
      if (buttonRef.current?.contains(target)) return;
      setIsOpen(false);
      setShowMaxMsg(false);
    };
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  }, [isOpen]);

  const activeAcct = connectedAccounts.find((a) => a.account_id === activeEmail);
  const isOffline = activeEmail ? offlineAccounts.has(activeEmail) : false;
  const isReconnectRequired = activeAcct?.auth_required ?? false;

  // Single exit point — all explicit close paths route here.
  const close = () => {
    setIsOpen(false);
    setShowMaxMsg(false);
  };

  return (
    <div className="sm:hidden relative flex-1 min-w-0">
      {/* Expanding pill trigger — fills mobile action row width */}
      <button
        ref={buttonRef}
        onClick={(e) => {
          e.stopPropagation();
          if (isOpen) {
            close();
          } else {
            setIsOpen(true);
          }
        }}
        aria-label={activeEmail ? 'Switch account' : 'Select account'}
        title={activeEmail ? 'Switch account' : 'Select account'}
        aria-expanded={isOpen}
        aria-haspopup="menu"
        className={`w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl border text-slate-200 active:scale-95 transition-all min-w-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:ring-offset-0 ${isOpen
          ? 'bg-white/[0.05] border-indigo-500/40 ring-1 ring-indigo-500/20'
          : 'bg-white/[0.03] border-white/10 hover:bg-white/[0.05]'
          }`}
      >
        {activeEmail ? (
          <span className="flex items-center gap-2 min-w-0 flex-1">
            <span
              className={`relative inline-flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br ${getAccountColor(activeEmail)} text-[9px] font-black text-white flex-shrink-0 shadow-md`}
            >
              {getEmailInitials(activeEmail)}
              <span
                className={`absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full ring-[1.5px] ring-[#0f172a] ${isReconnectRequired
                  ? 'bg-[#F59E0B]'
                  : isOffline
                    ? 'bg-[#EF4444]'
                    : 'bg-[#22C55E]'
                  }`}
              />
            </span>
            <span className="text-[11px] font-bold text-slate-300 truncate">
              {activeEmail.split('@')[0]}
            </span>
          </span>
        ) : (
          <span className="flex items-center gap-2 min-w-0 flex-1">
            <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-800 flex-shrink-0 ring-1 ring-white/10">
              <User size={12} className="text-slate-500" />
            </span>
            <span className="text-[11px] font-bold text-slate-500 truncate">Select account</span>
          </span>
        )}
        <ChevronDown
          size={10}
          className={`flex-shrink-0 text-slate-500 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Compact anchored popover — right-aligned below the trigger */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            ref={popoverRef}
            onPointerDown={(e) => e.stopPropagation()}
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.13, ease: 'easeOut' }}
            className="absolute right-0 top-full mt-2 w-56 rounded-2xl bg-[#0f172a] border border-white/10 shadow-2xl z-[100] overflow-hidden"
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
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
