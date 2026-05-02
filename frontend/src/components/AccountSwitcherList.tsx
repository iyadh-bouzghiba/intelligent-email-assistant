import { AlertCircle, LogOut } from 'lucide-react';
import { AccountInfo } from '@types';
import { getAccountColor, getEmailInitials } from './accountSwitcherHelpers';

interface Props {
  connectedAccounts: AccountInfo[];
  activeEmail: string | null;
  offlineAccounts: Set<string>;
  showMaxAccountsMsg: boolean;
  maxAccounts: number;
  authUrl: string;
  /** Called when the user clicks a non-auth-required account row to switch. */
  onSwitchAccount: (accountId: string) => void;
  /** Called when the user clicks the disconnect (LogOut) button. */
  onRequestDisconnect: (accountId: string) => void;
  /** Called when the user clicks "+ Add account" while already at max capacity. */
  onMaxAccountsAttempt: () => void;
  /** Called when auth_required account link is clicked — used to close the panel. */
  onClose: () => void;
}

/**
 * Shared account-list content used by both mobile (bottom-sheet) and desktop (dropdown).
 * Pure presentation — no switching logic, no open/close state.
 * All callbacks come from the parent surface component.
 */
export function AccountSwitcherList({
  connectedAccounts,
  activeEmail,
  offlineAccounts,
  showMaxAccountsMsg,
  maxAccounts,
  authUrl,
  onSwitchAccount,
  onRequestDisconnect,
  onMaxAccountsAttempt,
  onClose,
}: Props) {
  const sorted = [...connectedAccounts].sort((a, b) => {
    if (a.account_id === activeEmail) return -1;
    if (b.account_id === activeEmail) return 1;
    return 0;
  });

  return (
    <>
      {/* CRITICAL: Active account shown first, then others */}
      {sorted.map((info) => {
        const isActive = activeEmail === info.account_id;
        return (
          <div
            key={info.account_id}
            className={`flex items-center gap-3 px-4 py-3 hover:bg-white/[0.04] transition-colors ${isActive ? 'bg-indigo-500/10 border-l-2 border-indigo-500' : 'border-l-2 border-transparent'
              }`}
          >
            {/* Avatar + 4-state status dot */}
            <div className="relative flex-shrink-0">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br ${getAccountColor(info.account_id)} text-[10px] font-black text-white shadow-md`}
              >
                {getEmailInitials(info.account_id)}
              </div>
              {/* 4-state indicator: RECONNECT(amber) / CURRENT(green) / READY(blue) / OFFLINE(red) */}
              <span
                className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-[#0f172a] ${info.auth_required
                  ? 'bg-[#F59E0B]'
                  : offlineAccounts.has(info.account_id)
                    ? 'bg-[#EF4444]'
                    : isActive
                      ? 'bg-[#22C55E]'
                      : 'bg-[#3B82F6]'
                  }`}
                title={
                  info.auth_required
                    ? 'Reconnect required'
                    : offlineAccounts.has(info.account_id)
                      ? 'Offline'
                      : isActive
                        ? 'Current'
                        : 'Ready'
                }
              />
            </div>

            {info.auth_required ? (
              /* auth_required: link launches re-auth; NO switch logic */
              <a
                href={authUrl}
                onClick={onClose}
                className="flex-1 min-w-0 text-left rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60"
                title="Authentication expired — click to reconnect"
              >
                <div className="truncate text-xs font-bold text-amber-400">{info.account_id}</div>
                <div className="text-[9px] font-black text-[#F59E0B] uppercase tracking-wider mt-0.5">● Reconnect required</div>
              </a>
            ) : (
              <button
                onClick={() => onSwitchAccount(info.account_id)}
                className={`flex-1 min-w-0 text-left rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60 ${isActive ? 'text-indigo-400' : 'text-slate-300'}`}
              >
                <div className="truncate text-xs font-bold">{info.account_id}</div>
                {offlineAccounts.has(info.account_id) ? (
                  <div className="text-[9px] font-black text-[#EF4444] uppercase tracking-wider mt-0.5">● Offline</div>
                ) : isActive ? (
                  <div className="text-[9px] font-black text-[#22C55E] uppercase tracking-wider mt-0.5">● Current</div>
                ) : (
                  <div className="text-[9px] font-bold text-[#3B82F6] uppercase tracking-wider mt-0.5">● Ready</div>
                )}
              </button>
            )}

            <button
              onClick={() => onRequestDisconnect(info.account_id)}
              title={`Disconnect ${info.account_id}`}
              className="p-2 rounded-md text-slate-600 hover:text-rose-400 hover:bg-rose-500/10 transition-colors flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500/60"
            >
              <LogOut size={12} />
            </button>
          </div>
        );
      })}

      {/* Add account footer */}
      <div className="border-t border-white/5 px-4 py-3 space-y-2.5">
        {showMaxAccountsMsg && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-xl bg-rose-500/[0.08] border border-rose-500/20">
            <AlertCircle size={12} className="text-rose-400 mt-0.5 flex-shrink-0" />
            <p className="text-[10px] font-semibold text-rose-400 leading-snug">
              Maximum {maxAccounts} accounts reached. Disconnect one to add another.
            </p>
          </div>
        )}
        {connectedAccounts.length >= maxAccounts ? (
          <button
            onClick={onMaxAccountsAttempt}
            className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60 rounded"
          >
            + Add account
          </button>
        ) : (
          <a
            href={authUrl}
            className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60 rounded"
          >
            + Add account
          </a>
        )}
      </div>
    </>
  );
}
