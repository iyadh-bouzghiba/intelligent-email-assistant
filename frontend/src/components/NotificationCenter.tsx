import { useCallback, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Bell, BellOff, MailOpen, Trash2, TrendingUp, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmailViewModel } from '@types';

export interface NotificationCenterProps {
  items: EmailViewModel[];
  isOpen: boolean;
  unseenCount: number;
  notificationsEnabled: boolean;
  notificationsSupported: boolean;
  getItemId: (item: EmailViewModel) => string;
  isItemUnseen: (item: EmailViewModel) => boolean;
  hasUrgencyDelta: (item: EmailViewModel) => boolean;
  canMarkAsRead: (item: EmailViewModel) => boolean;
  onToggleOpen: () => void;
  onClose: () => void;
  onOpenItem: (item: EmailViewModel) => void;
  onDismissItem: (item: EmailViewModel) => void;
  onMarkAsRead: (item: EmailViewModel) => void;
  onToggleBrowserAlerts: () => void;
  buttonId?: string;
  panelId?: string;
}

export function NotificationCenter({
  items,
  isOpen,
  unseenCount,
  notificationsEnabled,
  notificationsSupported,
  getItemId,
  isItemUnseen,
  hasUrgencyDelta,
  canMarkAsRead,
  onToggleOpen,
  onClose,
  onOpenItem,
  onDismissItem,
  onMarkAsRead,
  onToggleBrowserAlerts,
  buttonId,
  panelId,
}: NotificationCenterProps) {
  const { t, i18n } = useTranslation();
  const bellButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const resolvedButtonId = buttonId ?? 'notification-center-button';
  const resolvedPanelId = panelId ?? 'notification-center-panel';
  const panelTitleId = `${resolvedPanelId}-title`;

  // Shared close + focus-restore helper used by outside click, Escape, and X button.
  const closePanelAndRestoreFocus = useCallback(() => {
    onClose();
    requestAnimationFrame(() => {
      bellButtonRef.current?.focus();
    });
  }, [onClose]);

  // Outside-click: close panel and restore focus when click lands outside.
  useEffect(() => {
    if (!isOpen) return;
    const handleMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (panelRef.current?.contains(target)) return;
      if (bellButtonRef.current?.contains(target)) return;
      closePanelAndRestoreFocus();
    };
    document.addEventListener('mousedown', handleMouseDown, true);
    return () => document.removeEventListener('mousedown', handleMouseDown, true);
  }, [isOpen, closePanelAndRestoreFocus]);

  // Escape: close panel and restore focus to bell button.
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      closePanelAndRestoreFocus();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closePanelAndRestoreFocus]);

  // ── Local helpers ─────────────────────────────────────────────────────────

  const locale = i18n.resolvedLanguage ?? i18n.language ?? 'en';

  const compactText = (value?: string | null): string => {
    if (!value) return '';
    return value.trim();
  };

  const getPrimaryLine = (item: EmailViewModel): string => {
    const action = compactText(item.action);
    if (action) return action;
    const subject = compactText(item.subject);
    if (subject) return subject;
    const sender = compactText(item.sender);
    if (sender) return sender;
    return t('notification.open_email');
  };

  const getUrgencyKey = (item: EmailViewModel): string => {
    const raw = item.ai_summary_json?.urgency?.trim().toLowerCase();
    if (raw === 'high') return 'inbox.urgency.high';
    if (raw === 'low') return 'inbox.urgency.low';
    if (item.priority === 'High') return 'inbox.urgency.high';
    if (item.priority === 'Low') return 'inbox.urgency.low';
    return 'inbox.urgency.medium';
  };

  const formatRelativeTime = (value?: string | null): string => {
    if (!value) return t('notification.just_now');
    const parsed = Date.parse(value);
    if (Number.isNaN(parsed)) return t('notification.just_now');
    const diffMs = Date.now() - parsed;
    const diffSecs = Math.round(diffMs / 1000);
    if (diffSecs < 60) return t('notification.just_now');
    try {
      const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
      const diffMins = Math.round(diffMs / 60000);
      if (Math.abs(diffMins) < 60) return rtf.format(-diffMins, 'minute');
      const diffHours = Math.round(diffMs / 3600000);
      if (Math.abs(diffHours) < 24) return rtf.format(-diffHours, 'hour');
      const diffDays = Math.round(diffMs / 86400000);
      return rtf.format(-diffDays, 'day');
    } catch {
      return t('notification.just_now');
    }
  };

  const getSecondaryTimestamp = (item: EmailViewModel): string =>
    formatRelativeTime(item.date_iso);

  // ── Derived display values ─────────────────────────────────────────────────

  const badgeLabel = unseenCount > 99 ? '99+' : String(unseenCount);

  const bellAriaLabel =
    unseenCount > 0
      ? `${t('notification.open')} — ${t('notification.unseen_count', { count: unseenCount > 99 ? '99+' : unseenCount })}`
      : t('notification.open');

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="relative flex-shrink-0">
      {/* Bell trigger button */}
      <button
        ref={bellButtonRef}
        id={resolvedButtonId}
        type="button"
        aria-label={bellAriaLabel}
        aria-expanded={isOpen}
        aria-controls={resolvedPanelId}
        aria-haspopup="dialog"
        onClick={onToggleOpen}
        className="relative inline-flex items-center justify-center h-[44px] w-[44px] rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.05] text-slate-200 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg"
      >
        <Bell size={16} aria-hidden="true" />
        {unseenCount > 0 && (
          <span
            aria-hidden="true"
            className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-primary-500 text-white text-[10px] font-black leading-none"
          >
            {badgeLabel}
          </span>
        )}
      </button>

      {/* Notification panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            ref={panelRef}
            id={resolvedPanelId}
            role="dialog"
            aria-labelledby={panelTitleId}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="absolute right-0 top-full mt-3 z-[300] w-[22rem] max-w-[calc(100vw-1.5rem)] rounded-2xl border border-white/10 bg-brand-surface shadow-2xl shadow-black/40 overflow-hidden"
          >
            {/* Panel header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
              <h2
                id={panelTitleId}
                className="text-[13px] font-black uppercase tracking-[0.16em] text-white"
              >
                {t('notification.title')}
              </h2>
              <button
                type="button"
                aria-label={t('notification.close')}
                onClick={closePanelAndRestoreFocus}
                className="inline-flex items-center justify-center h-[44px] w-[44px] rounded-xl text-slate-400 hover:text-white hover:bg-white/[0.06] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </div>

            {/* Browser-alerts section */}
            <div className="px-4 py-3 border-b border-white/[0.06]">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-bold text-slate-300 leading-tight">
                    {t('notification.browser_alerts')}
                  </p>
                  <p className="mt-0.5 text-[10px] text-slate-500 leading-snug">
                    {notificationsSupported
                      ? t('notification.browser_alerts_help')
                      : t('notification.permission_required')}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={onToggleBrowserAlerts}
                  disabled={!notificationsSupported}
                  className={`flex-shrink-0 inline-flex items-center gap-1.5 px-2.5 min-h-[44px] rounded-lg text-[10px] font-bold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60 ${
                    !notificationsSupported
                      ? 'text-slate-600 bg-white/[0.02] border border-white/[0.04] cursor-not-allowed'
                      : notificationsEnabled
                        ? 'text-primary-300 bg-primary-500/16 border border-primary-400/30 hover:bg-primary-500/24'
                        : 'text-slate-400 bg-white/[0.04] border border-white/[0.06] hover:bg-white/[0.07] hover:text-slate-200'
                  }`}
                >
                  {notificationsEnabled
                    ? <Bell size={10} aria-hidden="true" />
                    : <BellOff size={10} aria-hidden="true" />}
                  <span>
                    {notificationsEnabled
                      ? t('notification.browser_alerts_on')
                      : t('notification.browser_alerts_off')}
                  </span>
                </button>
              </div>
            </div>

            {/* Notification list or positive all-clear empty state */}
            <div className="overflow-y-auto max-h-[min(60vh,360px)] custom-scrollbar">
              {items.length === 0 ? (
                <div className="flex flex-col items-center justify-center px-6 py-8 text-center">
                  <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.04] border border-white/[0.06]">
                    <Bell size={18} className="text-slate-500" aria-hidden="true" />
                  </div>
                  <p className="text-sm font-semibold text-slate-300">
                    {t('notification.all_clear')}
                  </p>
                </div>
              ) : (
                <ul className="divide-y divide-white/[0.04]" role="list">
                  {items.map((item) => {
                    const id = getItemId(item);
                    const unseen = isItemUnseen(item);
                    const delta = hasUrgencyDelta(item);
                    const markable = canMarkAsRead(item);
                    const primaryLine = getPrimaryLine(item);
                    const timestamp = getSecondaryTimestamp(item);

                    return (
                      <li
                        key={id}
                        className={`relative ${unseen ? 'bg-primary-500/[0.04]' : ''}`}
                      >
                        {/* Main content: open-item button — action-first */}
                        <button
                          type="button"
                          onClick={() => onOpenItem(item)}
                          className="w-full text-left px-4 pt-3 pb-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500/60"
                        >
                          <div className="flex items-start gap-2 min-w-0">
                            <div className="flex-1 min-w-0">
                              {/* Primary line: action if present, else subject */}
                              <p
                                className={`text-[13px] leading-snug font-semibold truncate ${
                                  unseen ? 'text-white' : 'text-slate-200'
                                }`}
                              >
                                {primaryLine}
                              </p>
                              {/* Secondary line: sender · relative timestamp */}
                              <p className="mt-0.5 text-[11px] text-slate-400 truncate">
                                {item.sender && <span>{item.sender}</span>}
                                {item.sender && timestamp && (
                                  <span aria-hidden="true"> · </span>
                                )}
                                {timestamp && <span>{timestamp}</span>}
                              </p>
                              {/* Urgency label */}
                              <p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                                {t(getUrgencyKey(item))}
                              </p>
                            </div>
                            {/* Urgency delta indicator */}
                            {delta && (
                              <span
                                aria-hidden="true"
                                className="flex-shrink-0 mt-0.5 text-primary-400"
                              >
                                <TrendingUp size={13} aria-hidden="true" />
                              </span>
                            )}
                          </div>
                        </button>

                        {/* Row action buttons — separate from open button, no nesting */}
                        <div className="flex items-center gap-1 px-4 pb-2">
                          {markable && (
                            <button
                              type="button"
                              onClick={() => onMarkAsRead(item)}
                              aria-label={t('notification.mark_as_read')}
                              className="inline-flex items-center justify-center h-[44px] w-[44px] rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/[0.06] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60"
                            >
                              <MailOpen size={13} aria-hidden="true" />
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => onDismissItem(item)}
                            aria-label={t('notification.dismiss')}
                            className="inline-flex items-center justify-center h-[44px] w-[44px] rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/[0.06] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60"
                          >
                            <Trash2 size={13} aria-hidden="true" />
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
