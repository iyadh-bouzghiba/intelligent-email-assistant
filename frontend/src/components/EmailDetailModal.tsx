import { motion } from 'framer-motion';
import { X, Sparkles, MailOpen, Mail, RefreshCw } from 'lucide-react';
import { Briefing } from '@types';
import { FocusTrap } from './FocusTrap';
import { EmailQuickView } from './EmailQuickView';
import { EmailFullView } from './EmailFullView';
import { RefObject } from 'react';

interface Props {
  email: Briefing;
  panelView: 'quick' | 'full';
  detailIsSent: boolean;
  modifyScope: boolean;
  isRead: boolean;
  actionItemsRef: RefObject<HTMLDivElement>;
  isSummarizing?: boolean;
  readStatePending?: boolean;
  onClose: () => void;
  onSwitchView: (v: 'quick' | 'full') => void;
  onOpenReply: () => void;
  onSummarize: () => void;
  onMarkRead: () => void;
  onMarkUnread: () => void;
  getCategoryStyles: (cat: string) => string;
}

const TITLE_ID = 'email-detail-title';
const DESC_ID = 'email-detail-desc';

/**
 * Centered blocking modal dialog for email detail (read-only view).
 * Compose is handled separately by ReplyComposeModal.
 *
 * Accessibility contract:
 *   - role="dialog" + aria-modal="true"
 *   - aria-labelledby={TITLE_ID} → subject heading
 *   - aria-describedby={DESC_ID} → sender/date
 *   - FocusTrap: Tab cycle trapped, initial focus on close button
 *   - Backdrop does NOT close on click — only X / Escape (App.tsx)
 */
export function EmailDetailModal({
  email,
  panelView,
  detailIsSent,
  modifyScope,
  isRead,
  actionItemsRef,
  isSummarizing,
  readStatePending = false,
  onClose,
  onSwitchView,
  onOpenReply,
  onSummarize,
  onMarkRead,
  onMarkUnread,
  getCategoryStyles,
}: Props) {
  return (
    <>
      {/* Backdrop — aria-hidden so SR focus stays inside dialog */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[150] bg-black/70 backdrop-blur-sm"
        aria-hidden="true"
      />

      {/* Centering layer */}
      <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center p-0 sm:p-6 pointer-events-none">
        <FocusTrap initialFocusSelector="[data-modal-close]">
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 16 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            role="dialog"
            aria-modal="true"
            aria-labelledby={TITLE_ID}
            aria-describedby={DESC_ID}
            className="pointer-events-auto w-full h-full sm:h-auto sm:max-h-[90vh] sm:max-w-2xl bg-[#0f172a] border-0 sm:border sm:border-white/10 rounded-none sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden"
          >
            {/* ── Header ───────────────────────────────────────────────────── */}
            <div className="flex-shrink-0 bg-[#0f172a] border-b border-white/5 px-4 py-4 sm:px-6 sm:py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h2 id={TITLE_ID} className="text-xl font-black text-white mb-2 leading-tight">
                    {email.subject}
                  </h2>
                  <div id={DESC_ID} className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
                    <span className="font-semibold text-slate-300">{email.sender}</span>
                    <span className="text-slate-600">|</span>
                    <span>{email.date}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 mt-3">
                    <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${
                      email.priority === 'High'   ? 'bg-[#FF3B5C] text-white border-[#FF3B5C]' :
                      email.priority === 'Medium' ? 'bg-[#FFB800] text-[#1a1a1a] border-[#FFB800]' :
                                                    'bg-[#3D4A5C] text-[#94A3B8] border-[#3D4A5C]'
                    }`}>
                      {email.priority}
                    </span>
                    <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${getCategoryStyles(email.category)}`}>
                      {email.category}
                    </span>
                    {detailIsSent && (
                      <span className="px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border bg-slate-500/10 text-slate-400 border-slate-500/20">
                        Sent
                      </span>
                    )}
                    {!detailIsSent && (
                      <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${
                        isRead
                          ? 'bg-slate-500/10 text-slate-500 border-slate-500/20'
                          : 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
                      }`}>
                        {isRead ? 'Read' : 'Unread'}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  data-modal-close
                  onClick={onClose}
                  aria-label="Close email details"
                  className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 sm:p-2 rounded-xl hover:bg-white/10 text-slate-400 hover:text-white transition-colors flex-shrink-0"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* ── Scrollable body ───────────────────────────────────────────── */}
            <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-6 space-y-8 min-h-0 sm:px-8 sm:py-8">
              {panelView === 'quick' ? (
                <EmailQuickView
                  email={email}
                  actionItemsRef={actionItemsRef}
                  onReadFull={() => onSwitchView('full')}
                  isSummarizing={isSummarizing}
                />
              ) : (
                <EmailFullView
                  email={email}
                  actionItemsRef={actionItemsRef}
                  onBackToSummary={() => onSwitchView('quick')}
                />
              )}
            </div>

            {/* ── Footer: action bar ────────────────────────────────────────── */}
            <div className="flex-shrink-0 border-t border-white/[0.12] bg-[#0f172a] px-4 py-3 sm:px-6 sm:py-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
              {/* Left: Close + Summarize + read/unread toggle */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={onClose}
                  className="inline-flex items-center justify-center min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all"
                >
                  Close
                </button>
                {email.ai_summary_text && email.gmail_message_id && (
                  <button
                    onClick={onSummarize}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all"
                  >
                    <Sparkles size={12} />
                    Re-summarize
                  </button>
                )}
                {modifyScope && !detailIsSent && (
                  isRead ? (
                    <button
                      onClick={onMarkUnread}
                      disabled={readStatePending}
                      className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Mark as unread"
                    >
                      {readStatePending ? <RefreshCw size={12} className="animate-spin" /> : <Mail size={12} />}
                      Mark Unread
                    </button>
                  ) : (
                    <button
                      onClick={onMarkRead}
                      disabled={readStatePending}
                      className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Mark as read"
                    >
                      {readStatePending ? <RefreshCw size={12} className="animate-spin" /> : <MailOpen size={12} />}
                      Mark Read
                    </button>
                  )
                )}
              </div>

              {/* Right: view switch / Draft Reply */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {panelView === 'quick' ? (
                  <button
                    onClick={() => onSwitchView('full')}
                    className="inline-flex items-center justify-center min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-white/[0.06] border border-white/10 text-slate-300 hover:text-white hover:bg-white/10 text-xs font-bold transition-all"
                  >
                    Read full email
                  </button>
                ) : !detailIsSent ? (
                  <button
                    onClick={onOpenReply}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-bold transition-all shadow-lg shadow-indigo-600/20"
                  >
                    <Mail size={12} />
                    Draft Reply
                  </button>
                ) : null}
              </div>
            </div>
          </motion.div>
        </FocusTrap>
      </div>
    </>
  );
}
