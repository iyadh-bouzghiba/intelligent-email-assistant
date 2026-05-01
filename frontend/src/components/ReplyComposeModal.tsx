import { RefObject, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { X, AlertCircle, RefreshCw, Mail, Sparkles, ChevronDown, Save, Trash2 } from 'lucide-react';
import { Briefing, DraftTone, SupportedTone, EmailTemplate } from '@types';
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
   * P4 optional controlled tone/template contract.
   * These remain optional until App.tsx becomes the shared state owner in FILE 5.
   */
  selectedTone?: DraftTone;
  availableTones?: SupportedTone[];
  onToneChange?: (tone: DraftTone) => void;
  templates?: EmailTemplate[];
  templatesLoading?: boolean;
  templatesError?: string | null;
  templateSaving?: boolean;
  templateDeletingId?: string | null;
  onApplyTemplate?: (template: EmailTemplate) => void;
  onSaveTemplate?: (name: string) => Promise<void> | void;
  onDeleteTemplate?: (templateId: string) => Promise<void> | void;

  /**
   * sanitizeOriginalExcerpt is intentionally NOT a prop here.
   * It belongs only in the send path (buildOutboundBody in App.tsx).
   * This component uses email.body directly for display, normalized via normalizeBodyText.
   */
  buildAttribution: (date: string, sender: string) => string;
}

const TITLE_ID = 'reply-compose-title';

const FALLBACK_TONES: SupportedTone[] = [
  { code: 'professional', label: 'Professional' },
  { code: 'casual', label: 'Casual' },
  { code: 'concise', label: 'Concise' },
  { code: 'empathetic', label: 'Empathetic' },
];

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
 *
 * P4 contract:
 *   - Tone/template controls are presentation-only here
 *   - Shared state ownership belongs in App.tsx (FILE 5)
 *   - This component may hold ephemeral local UI state only
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
  selectedTone,
  availableTones,
  onToneChange,
  templates,
  templatesLoading = false,
  templatesError = null,
  templateSaving = false,
  templateDeletingId = null,
  onApplyTemplate,
  onSaveTemplate,
  onDeleteTemplate,
  buildAttribution,
}: Props) {
  const [showQuoted, setShowQuoted] = useState(false);
  const [localTone, setLocalTone] = useState<DraftTone>('professional');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [showSaveTemplateForm, setShowSaveTemplateForm] = useState(false);
  const [templateName, setTemplateName] = useState('');

  const toneOptions = availableTones && availableTones.length > 0 ? availableTones : FALLBACK_TONES;
  const effectiveTone: DraftTone = selectedTone ?? localTone;
  const templateOptions = templates ?? [];

  useEffect(() => {
    setSelectedTemplateId('');
    setShowSaveTemplateForm(false);
    setTemplateName('');
  }, [email.thread_id]);

  const selectedTemplate = useMemo(
    () => templateOptions.find((template) => template.id === selectedTemplateId) ?? null,
    [templateOptions, selectedTemplateId]
  );

  const handleToneSelection = (tone: DraftTone) => {
    if (onToneChange) {
      onToneChange(tone);
      return;
    }
    setLocalTone(tone);
  };

  const handleApplySelectedTemplate = () => {
    if (!selectedTemplate || !onApplyTemplate) return;
    onApplyTemplate(selectedTemplate);
  };

  const handleSaveTemplate = async () => {
    if (!onSaveTemplate) return;
    const trimmed = templateName.trim();
    if (!trimmed) return;
    await onSaveTemplate(trimmed);
    setTemplateName('');
    setShowSaveTemplateForm(false);
  };

  const handleDeleteSelectedTemplate = async () => {
    if (!selectedTemplate?.id || !onDeleteTemplate) return;
    await onDeleteTemplate(selectedTemplate.id);
    setSelectedTemplateId('');
  };

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
                  className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 sm:p-2 rounded-xl hover:bg-white/10 text-slate-400 hover:text-white transition-colors flex-shrink-0"
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

              {templatesError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs">
                  <AlertCircle size={13} className="flex-shrink-0" />
                  <span className="font-bold">{templatesError}</span>
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

              {/* Draft tools */}
              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] px-3 py-3 sm:px-4 sm:py-4 space-y-3">
                <div className="space-y-1">
                  <p className="text-[10px] font-black text-indigo-300 uppercase tracking-[0.2em]">
                    Draft Tools
                  </p>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Adjust tone, apply a saved template, or save this reply for faster reuse.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      Tone
                    </label>

                    <div
                      role="radiogroup"
                      aria-label="Reply tone"
                      className="flex flex-wrap gap-2"
                    >
                      {toneOptions.map((tone) => {
                        const isSelected = effectiveTone === tone.code;

                        return (
                          <button
                            key={tone.code}
                            type="button"
                            role="radio"
                            aria-checked={isSelected}
                            disabled={sending}
                            onClick={() => handleToneSelection(tone.code)}
                            className={`min-h-[40px] px-3 py-2 rounded-xl text-xs font-bold transition-all border ${isSelected
                              ? 'bg-indigo-600/90 border-indigo-400/60 text-white shadow-md shadow-indigo-900/20'
                              : 'bg-white/[0.03] border-white/10 text-slate-300 hover:text-white hover:bg-white/[0.06]'
                              } ${sending ? 'opacity-50 cursor-not-allowed' : ''}`}
                          >
                            {tone.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      Template
                    </label>
                    <select
                      value={selectedTemplateId}
                      onChange={(e) => setSelectedTemplateId(e.target.value)}
                      disabled={templatesLoading || templateOptions.length === 0}
                      className="w-full px-3 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500/40 disabled:opacity-50 transition-all"
                    >
                      <option value="" className="bg-slate-900 text-slate-200">
                        {templatesLoading
                          ? 'Loading templates…'
                          : templateOptions.length > 0
                            ? 'Select a template'
                            : 'No templates saved yet — write a reply, then tap Save as Template to reuse it later.'}
                      </option>
                      {templateOptions.map((template) => (
                        <option
                          key={template.id ?? `${template.name}-${template.language}`}
                          value={template.id ?? ''}
                          className="bg-slate-900 text-slate-200"
                        >
                          {template.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2">
                  <button
                    type="button"
                    onClick={handleApplySelectedTemplate}
                    disabled={!selectedTemplate || !onApplyTemplate}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[40px] px-4 rounded-xl bg-indigo-600/90 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold transition-all shadow-md shadow-indigo-900/20"
                  >
                    <Sparkles size={12} />
                    Apply Template
                  </button>

                  <button
                    type="button"
                    onClick={() => setShowSaveTemplateForm((v) => !v)}
                    disabled={!onSaveTemplate}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[40px] px-4 rounded-xl bg-white/[0.04] border border-white/10 text-slate-300 hover:text-white hover:bg-white/[0.07] disabled:opacity-40 disabled:cursor-not-allowed text-xs font-bold transition-all"
                  >
                    <Save size={12} />
                    Save as Template
                  </button>

                  <button
                    type="button"
                    onClick={handleDeleteSelectedTemplate}
                    disabled={!selectedTemplate?.id || !onDeleteTemplate || templateDeletingId === selectedTemplate?.id}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[40px] px-4 rounded-xl bg-rose-500/[0.06] border border-rose-500/20 text-rose-300 hover:text-rose-200 hover:bg-rose-500/[0.1] disabled:opacity-40 disabled:cursor-not-allowed text-xs font-bold transition-all"
                  >
                    {templateDeletingId === selectedTemplate?.id ? (
                      <>
                        <RefreshCw size={12} className="animate-spin" />
                        Deleting…
                      </>
                    ) : (
                      <>
                        <Trash2 size={12} />
                        Delete Template
                      </>
                    )}
                  </button>
                </div>

                {showSaveTemplateForm && (
                  <div className="space-y-2 rounded-xl border border-white/[0.08] bg-black/10 px-3 py-3">
                    <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      Template Name
                    </label>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input
                        type="text"
                        value={templateName}
                        onChange={(e) => setTemplateName(e.target.value)}
                        placeholder="e.g. Security acknowledgment"
                        disabled={templateSaving}
                        className="flex-1 px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 disabled:opacity-50 transition-all"
                      />
                      <button
                        type="button"
                        onClick={handleSaveTemplate}
                        disabled={!templateName.trim() || templateSaving || !onSaveTemplate}
                        className="inline-flex items-center justify-center gap-1.5 min-h-[40px] px-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold transition-all"
                      >
                        {templateSaving ? (
                          <>
                            <RefreshCw size={12} className="animate-spin" />
                            Saving…
                          </>
                        ) : (
                          <>
                            <Save size={12} />
                            Save
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-indigo-500/[0.14] bg-white/[0.035] px-3 py-3 sm:px-4 sm:py-4 space-y-2 shadow-lg shadow-black/10">
                <div className="space-y-1">
                  <p className="text-[10px] font-black text-indigo-300 uppercase tracking-[0.2em]">
                    Reply Body
                  </p>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Write, review, and refine your final reply before sending.
                  </p>
                </div>

                <textarea
                  ref={replyTextareaRef}
                  value={replyBody}
                  onChange={(e) => onReplyBodyChange(e.target.value)}
                  placeholder="Write your reply here…"
                  rows={6}
                  className="w-full min-h-[220px] resize-none bg-transparent border-0 p-0 text-sm leading-relaxed text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-0"
                />
              </div>

              {/* —— Reference context —— read-only, never included in outbound body —— */}
              {hasReference && (
                <div className="border-t border-white/[0.06] pt-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.18em] select-none">
                      Reference — not sent
                    </p>
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em]">
                      Tone: {toneOptions.find((tone) => tone.code === effectiveTone)?.label ?? effectiveTone}
                    </span>
                  </div>

                  {/* AI summary + action items — always visible when present */}
                  {hasAiSummary && (
                    <div className="space-y-2">
                      <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-white/[0.025] border border-white/[0.06]">
                        <Sparkles size={10} className="text-indigo-300 mt-0.5 flex-shrink-0" />
                        <p className="text-xs text-slate-300/85 leading-relaxed">
                          {email.ai_summary_text}
                        </p>
                      </div>

                      {email.ai_summary_json?.action_items && email.ai_summary_json.action_items.length > 0 && (
                        <div className="px-3 py-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05] space-y-1.5">
                          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em]">
                            Action items
                          </p>
                          <ol className="space-y-1 list-decimal list-inside">
                            {email.ai_summary_json.action_items.map((action: string, idx: number) => (
                              <li key={idx} className="text-xs text-slate-400 leading-relaxed">
                                {action}
                              </li>
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
                          className="flex items-center gap-1 text-[10px] font-semibold text-slate-500 hover:text-slate-300 transition-colors"
                          aria-expanded={showQuoted}
                        >
                          <ChevronDown
                            size={11}
                            className={`transition-transform duration-150 ${showQuoted ? 'rotate-180' : ''}`}
                          />
                          {showQuoted ? 'Hide original' : 'Show original'}
                        </button>

                        {showQuoted && (
                          <div className="mt-2 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3">
                            <div className="py-2.5 space-y-1.5">
                              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em] select-none">
                                {buildAttribution(email.date || '', email.sender || '')}
                              </p>
                              <div className="max-h-56 overflow-y-auto custom-scrollbar pr-1">
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
                      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3">
                        <div className="py-2.5 space-y-1.5">
                          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em] select-none">
                            {buildAttribution(email.date || '', email.sender || '')}
                          </p>
                          <div className="max-h-56 overflow-y-auto custom-scrollbar pr-1">
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

            {/* Footer — action bar
                Mobile: flex-col-reverse stacks Send on top (full-width) and Discard below.
                sm+: flex-row with Discard left, Send right — standard desktop pattern. */}
            <div className="flex-shrink-0 border-t border-white/[0.12] bg-[#0f172a] px-4 py-3 sm:px-6 sm:py-4 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-2.5 sm:gap-3">
              <button
                onClick={onDiscard}
                disabled={sending}
                className="w-full sm:w-auto inline-flex items-center justify-center min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all"
              >
                Discard
              </button>
              <button
                onClick={onSend}
                disabled={sending || !replyBody.trim() || !email.thread_id}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition-all shadow-lg shadow-indigo-600/20"
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
