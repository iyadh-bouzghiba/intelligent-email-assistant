import { RefObject } from 'react';
import { motion } from 'framer-motion';
import { X, AlertCircle, RefreshCw, Mail } from 'lucide-react';
import { Briefing } from '@types';
import { FocusTrap } from './FocusTrap';

interface Props {
  email: Briefing;
  replyBody: string;
  replySubject: string;
  replyCC: string;
  sending: boolean;
  panelError: string | null;
  replyTextareaRef: RefObject<HTMLTextAreaElement>;
  onDiscard: () => void;
  onSend: () => void;
  onReplyBodyChange: (v: string) => void;
  onReplySubjectChange: (v: string) => void;
  onReplyCCChange: (v: string) => void;
  sanitizeOriginalExcerpt: (body: string) => string;
  buildAttribution: (date: string, sender: string) => string;
}

const TITLE_ID = 'reply-compose-title';

/**
 * Standalone blocking modal for composing a reply.
 *
 * Accessibility contract:
 *   - role="dialog" + aria-modal="true"
 *   - aria-labelledby={TITLE_ID} points to "Reply" heading
 *   - FocusTrap traps Tab cycle; initial focus on textarea
 *   - Backdrop does NOT close on click — only X button / Escape (via App.tsx)
 *
 * Layout mirrors EmailDetailModal: full-screen mobile, centered sm+.
 */
export function ReplyComposeModal({
  email,
  replyBody,
  replySubject,
  replyCC,
  sending,
  panelError,
  replyTextareaRef,
  onDiscard,
  onSend,
  onReplyBodyChange,
  onReplySubjectChange,
  onReplyCCChange,
  sanitizeOriginalExcerpt,
  buildAttribution,
}: Props) {
  return (
    <>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[150] bg-black/70 backdrop-blur-sm"
        aria-hidden="true"
      />

      {/* Centering layer */}
      <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center p-0 sm:p-6 pointer-events-none">
        <FocusTrap initialFocusSelector="textarea">
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 16 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            role="dialog"
            aria-modal="true"
            aria-labelledby={TITLE_ID}
            className="pointer-events-auto w-full h-full sm:h-auto sm:max-h-[90vh] sm:max-w-2xl bg-[#0f172a] border-0 sm:border sm:border-white/10 rounded-none sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex-shrink-0 bg-[#0f172a] border-b border-white/5 px-6 py-4">
              <div className="flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h2 id={TITLE_ID} className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                    Reply
                  </h2>
                  <p className="text-sm font-semibold text-slate-300 mt-0.5 truncate">{email.subject}</p>
                  <p className="text-xs text-slate-500 mt-0.5">to {email.sender}</p>
                </div>
                <button
                  onClick={onDiscard}
                  disabled={sending}
                  aria-label="Discard draft"
                  className="p-2 rounded-xl hover:bg-white/10 text-slate-400 hover:text-white transition-colors flex-shrink-0"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Scrollable compose area */}
            <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-4 space-y-3 min-h-0">
              {panelError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
                  <AlertCircle size={13} className="flex-shrink-0" />
                  <span className="font-bold">{panelError}</span>
                </div>
              )}
              <input
                type="text"
                value={replySubject}
                onChange={(e) => onReplySubjectChange(e.target.value)}
                placeholder="Subject"
                className="w-full px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
              />
              <input
                type="text"
                value={replyCC}
                onChange={(e) => onReplyCCChange(e.target.value)}
                placeholder="Cc (optional — comma or semicolon separated)"
                className="w-full px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
              />
              <textarea
                ref={replyTextareaRef}
                value={replyBody}
                onChange={(e) => onReplyBodyChange(e.target.value)}
                placeholder="Write your reply here…"
                rows={6}
                className="w-full p-3 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
              />

              {/* Quoted original */}
              {email.body && (() => {
                const excerpt = sanitizeOriginalExcerpt(email.body);
                return excerpt ? (
                  <div className="border-t border-white/[0.08] pt-3">
                    <div className="pl-3 border-l-2 border-indigo-500/40 bg-white/[0.03] py-2 pr-3 rounded-r-lg space-y-1">
                      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider select-none">
                        {buildAttribution(email.date || '', email.sender || '')}
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed line-clamp-5 whitespace-pre-wrap select-none">
                        {excerpt}
                      </p>
                    </div>
                  </div>
                ) : null;
              })()}
            </div>

            {/* Footer — action bar */}
            <div className="flex-shrink-0 border-t border-white/[0.12] bg-[#0f172a] px-6 py-4 flex items-center justify-between gap-3">
              <button
                onClick={onDiscard}
                disabled={sending}
                className="px-4 py-2 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all"
              >
                Discard
              </button>
              <button
                onClick={onSend}
                disabled={sending || !replyBody.trim() || !email.thread_id}
                className="px-5 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition-all shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-1.5 min-w-[120px]"
              >
                {sending ? (
                  <>
                    <RefreshCw size={12} className="animate-spin" />
                    Sending...
                  </>
                ) : (
                  <>
                    <Mail size={12} />
                    Send Reply
                  </>
                )}
              </button>
            </div>
          </motion.div>
        </FocusTrap>
      </div>
    </>
  );
}
