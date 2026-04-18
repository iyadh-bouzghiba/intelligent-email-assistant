import { RefObject, useState } from 'react';
import { motion } from 'framer-motion';
import { X, AlertCircle, RefreshCw, Mail, Sparkles, ChevronDown } from 'lucide-react';
import { Briefing } from '@types';
import { FocusTrap } from './FocusTrap';
import { normalizeBodyText } from '@utils/normalizeBodyText';

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
  /**
   * sanitizeOriginalExcerpt is intentionally NOT a prop here.
   * It belongs only in the send path (buildOutboundBody in App.tsx).
   * This component uses email.body directly for display, normalized via normalizeBodyText.
   */
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
 * Reference context (read-only — never included in outbound body):
 *   - If AI summary exists: show summary + action items always visible;
 *     original quoted context hidden behind a disclosure toggle by default
 *   - If no AI summary: show quoted original directly (no toggle needed)
 *   - normalizeBodyText() applied to excerpt for display only;
 *     sanitizeOriginalExcerpt contract for outbound send is untouched
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
  buildAttribution,
}: Props) {
  const [showQuoted, setShowQuoted] = useState(false);

  // Display-only: full original message, normalized for rendering.
  // sanitizeOriginalExcerpt is NOT used here — that function belongs exclusively in
  // the send path (buildOutboundBody in App.tsx) where it caps and strips thread history.
  // Here we show the full body so the user has complete context when composing.
  const displayBody = normalizeBodyText(email.body || '');

  const hasAiSummary = !!email.ai_summary_text;
  const hasExcerpt = !!displayBody;
  const hasReference = hasAiSummary || hasExcerpt;
  // When AI summary exists, original message is shown behind a disclosure toggle
  const quotedNeedsToggle = hasAiSummary && hasExcerpt;

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
            <div className="flex-shrink-0 bg-[#0f172a] border-b border-white/5 px-4 py-4 sm:px-6">
              <div className="flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h2 id={TITLE_ID} className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                    Reply
                  </h2>
                  <p className="text-sm font-semibold text-slate-300 mt-0.5 truncate">{email.subject}</p>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">to {email.sender}</p>
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
            <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-4 sm:px-6 space-y-3 min-h-0">
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

              {/* ── Reference context ── read-only, never included in outbound body ── */}
              {hasReference && (
                <div className="border-t border-white/[0.08] pt-3 space-y-2">
                  <p className="text-[9px] font-black text-slate-600 uppercase tracking-widest select-none">
                    Reference — not sent
                  </p>

                  {/* AI summary + action items — always visible when present */}
                  {hasAiSummary && (
                    <div className="space-y-2">
                      <div className="flex items-start gap-2 px-3 py-2 rounded-xl bg-indigo-500/[0.06] border border-indigo-500/[0.12]">
                        <Sparkles size={10} className="text-indigo-400 mt-0.5 flex-shrink-0" />
                        <p className="text-xs text-indigo-300/80 leading-relaxed">
                          {email.ai_summary_text}
                        </p>
                      </div>
                      {email.ai_summary_json?.action_items && email.ai_summary_json.action_items.length > 0 && (
                        <div className="px-3 py-2 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-1">
                          <p className="text-[9px] font-black text-slate-500 uppercase tracking-wider">Action items</p>
                          <ol className="space-y-0.5 list-decimal list-inside">
                            {email.ai_summary_json.action_items.map((action: string, idx: number) => (
                              <li key={idx} className="text-xs text-slate-400 leading-relaxed">{action}</li>
                            ))}
                          </ol>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Original message — full body, display-only, never sent.
                      Direct when no AI summary; behind disclosure toggle when AI summary present. */}
                  {hasExcerpt && (
                    quotedNeedsToggle ? (
                      <div>
                        <button
                          type="button"
                          onClick={() => setShowQuoted(v => !v)}
                          className="flex items-center gap-1 text-[10px] font-semibold text-slate-500 hover:text-slate-400 transition-colors"
                          aria-expanded={showQuoted}
                        >
                          <ChevronDown
                            size={11}
                            className={`transition-transform duration-150 ${showQuoted ? 'rotate-180' : ''}`}
                          />
                          {showQuoted ? 'Hide original' : 'Show original'}
                        </button>
                        {showQuoted && (
                          <div className="mt-2 pl-3 border-l-2 border-indigo-500/30 bg-white/[0.03] rounded-r-lg">
                            <div className="py-2 pr-3 space-y-1.5">
                              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider select-none">
                                {buildAttribution(email.date || '', email.sender || '')}
                              </p>
                              <div className="max-h-56 overflow-y-auto custom-scrollbar">
                                <p className="text-xs text-slate-400 leading-relaxed whitespace-pre-wrap break-words">
                                  {displayBody}
                                </p>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      /* No AI summary — show full original message directly */
                      <div className="pl-3 border-l-2 border-indigo-500/30 bg-white/[0.03] rounded-r-lg">
                        <div className="py-2 pr-3 space-y-1.5">
                          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider select-none">
                            {buildAttribution(email.date || '', email.sender || '')}
                          </p>
                          <div className="max-h-56 overflow-y-auto custom-scrollbar">
                            <p className="text-xs text-slate-400 leading-relaxed whitespace-pre-wrap break-words">
                              {displayBody}
                            </p>
                          </div>
                        </div>
                      </div>
                    )
                  )}
                </div>
              )}
            </div>

            {/* Footer — action bar */}
            <div className="flex-shrink-0 border-t border-white/[0.12] bg-[#0f172a] px-4 py-3 sm:px-6 sm:py-4 flex items-center justify-between gap-3">
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
