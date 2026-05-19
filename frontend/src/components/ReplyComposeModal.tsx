import { RefObject, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { X, AlertCircle, RefreshCw, Mail, Sparkles, ChevronDown, Save, Trash2, Paperclip } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmailViewModel, DraftTone, SupportedTone, EmailTemplate, ReplyAttachmentDraft } from '@types';
import { FocusTrap } from './FocusTrap';
import { normalizeBodyText } from '@utils/normalizeBodyText';
import { deriveThreadContext } from '@utils/deriveThreadContext';
import AiSummaryConfidence from './AiSummaryConfidence';
import ThreadContextSignal from './ThreadContextSignal';

interface Props {
  email: EmailViewModel;
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
  onSaveTemplate?: (name: string) => Promise<boolean> | boolean;
  onDeleteTemplate?: (templateId: string) => Promise<void> | void;

  /**
   * sanitizeOriginalExcerpt is intentionally NOT a prop here.
   * It belongs only in the send path (buildOutboundBody in App.tsx).
   * This component uses email.body directly for display, normalized via normalizeBodyText.
   */
  buildAttribution: (date: string, sender: string) => string;

  /**
   * P5.4 optional controlled attachment UI contract.
   * All props remain optional — App.tsx wiring deferred to a later slice.
   */
  attachments?: ReplyAttachmentDraft[];
  attachmentError?: string | null;
  attachmentsTotalBytes?: number;
  attachmentsDisabled?: boolean;
  onAddAttachments?: (files: File[]) => void;
  onRemoveAttachment?: (index: number) => void;
  accountEmail?: string;
}

const TITLE_ID = 'reply-compose-title';

const EMPTY_TEMPLATES: EmailTemplate[] = [];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

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
  attachments = [],
  attachmentError = null,
  attachmentsTotalBytes = 0,
  attachmentsDisabled = false,
  onAddAttachments,
  onRemoveAttachment,
  accountEmail,
}: Props) {
  const { t } = useTranslation();

  const [showQuoted, setShowQuoted] = useState(false);
  const [localTone, setLocalTone] = useState<DraftTone>('professional');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [showSaveTemplateForm, setShowSaveTemplateForm] = useState(false);
  const [templateName, setTemplateName] = useState('');

  const translatedFallbackTones: SupportedTone[] = [
    { code: 'professional', label: t('compose.tone_professional') },
    { code: 'casual', label: t('compose.tone_casual') },
    { code: 'concise', label: t('compose.tone_concise') },
    { code: 'empathetic', label: t('compose.tone_empathetic') },
  ];

  const toneOptions = availableTones && availableTones.length > 0 ? availableTones : translatedFallbackTones;
  const effectiveTone: DraftTone = selectedTone ?? localTone;

  const getToneDisplayLabel = (tone: SupportedTone) => {
    switch (tone.code) {
      case 'professional': return t('compose.tone_professional');
      case 'casual': return t('compose.tone_casual');
      case 'concise': return t('compose.tone_concise');
      case 'empathetic': return t('compose.tone_empathetic');
      default: return tone.label;
    }
  };
  const templateOptions = templates ?? EMPTY_TEMPLATES;
  const hasSaveTemplateHandler = typeof onSaveTemplate === 'function';
  const hasSaveableReplyBody = replyBody.trim().length > 0;
  const canToggleSaveTemplateForm =
    hasSaveTemplateHandler &&
    hasSaveableReplyBody &&
    !templateSaving;
  const canSubmitTemplateSave =
    canToggleSaveTemplateForm &&
    templateName.trim().length > 0;

  useEffect(() => {
    setSelectedTemplateId('');
    setShowSaveTemplateForm(false);
    setTemplateName('');
  }, [email.thread_id]);

  const selectedTemplate = useMemo(
    () => templateOptions.find((template) => template.id === selectedTemplateId) ?? null,
    [templateOptions, selectedTemplateId]
  );

  const threadContext = useMemo(
    () => deriveThreadContext(email, accountEmail),
    [email, accountEmail]
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
    const saveTemplate = onSaveTemplate;
    if (!saveTemplate || !hasSaveableReplyBody || templateSaving) return;

    const trimmed = templateName.trim();
    if (!trimmed) return;

    const didSave = await saveTemplate(trimmed);
    if (!didSave) return;

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
            className="pointer-events-auto w-full h-full sm:h-auto sm:max-h-[90vh] sm:max-w-2xl bg-brand-surface border-0 sm:border sm:border-brand-border rounded-none sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex-shrink-0 bg-brand-surface border-b border-white/5 px-4 py-4 sm:px-6">
              <div className="flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h2 id={TITLE_ID} className="text-xs font-semibold text-primary-400 uppercase tracking-wider">
                    {t('compose.reply')}
                  </h2>
                  <p className="text-sm font-semibold text-slate-300 mt-0.5 truncate">{email.subject}</p>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{t('compose.to_sender', { sender: email.sender })}</p>
                </div>
                <button
                  onClick={onDiscard}
                  disabled={sending}
                  aria-label={t('compose.discard_draft')}
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
                id="reply-subject-input"
                name="replySubject"
                type="text"
                value={replySubject}
                onChange={(e) => onReplySubjectChange(e.target.value)}
                aria-label={t('compose.subject')}
                placeholder={t('compose.subject')}
                className="w-full px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
              />

              <input
                id="reply-cc-input"
                name="replyCC"
                type="text"
                value={replyCC}
                onChange={(e) => onReplyCCChange(e.target.value)}
                aria-label={t('compose.cc')}
                placeholder={t('compose.cc_placeholder')}
                className="w-full px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
              />

              {/* Draft tools */}
              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5 sm:px-4 sm:py-3 space-y-2.5">
                <div className="space-y-1">
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.18em]">
                    {t('compose.tools_title')}
                  </p>
                  <p className="text-[11px] text-slate-500 leading-relaxed">
                    {t('compose.tools_description')}
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <p id="reply-tone-group-label" className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      {t('compose.tone')}
                    </p>

                    <div
                      role="radiogroup"
                      aria-labelledby="reply-tone-group-label"
                      className="grid grid-cols-2 gap-2"
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
                            className={`w-full min-w-0 min-h-[40px] px-3 py-2 rounded-xl text-xs font-bold leading-tight text-center whitespace-normal break-words flex items-center justify-center transition-all border ${isSelected
                              ? 'bg-primary-500/15 border-primary-400/30 text-primary-200'
                              : 'bg-white/[0.02] border-white/[0.08] text-slate-300 hover:text-white hover:bg-white/[0.05]'
                              } ${sending ? 'opacity-50 cursor-not-allowed' : ''}`}
                          >
                            {getToneDisplayLabel(tone)}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label htmlFor="reply-template-select" className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      {t('compose.template')}
                    </label>
                    <select
                      id="reply-template-select"
                      name="selectedTemplateId"
                      value={selectedTemplateId}
                      onChange={(e) => setSelectedTemplateId(e.target.value)}
                      disabled={templatesLoading || templateOptions.length === 0}
                      className="w-full px-3 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500/40 disabled:opacity-50 transition-all"
                    >
                      <option value="" className="bg-slate-900 text-slate-200">
                        {templatesLoading
                          ? t('compose.loading_templates')
                          : templateOptions.length > 0
                            ? t('compose.select_template')
                            : t('compose.no_templates_saved')}
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

                    {!templatesLoading && templateOptions.length === 0 && (
                      <p className="text-[11px] leading-relaxed text-slate-500">
                        {t('compose.empty_templates_help')}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2">
                  <button
                    type="button"
                    onClick={handleApplySelectedTemplate}
                    disabled={!selectedTemplate || !onApplyTemplate}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[40px] px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-200 hover:text-white hover:bg-white/[0.08] disabled:opacity-40 disabled:cursor-not-allowed text-xs font-bold transition-all"
                  >
                    <Sparkles size={12} />
                    {t('compose.apply_template')}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      if (!canToggleSaveTemplateForm) return;
                      setShowSaveTemplateForm((v) => !v);
                    }}
                    disabled={!canToggleSaveTemplateForm}
                    className="inline-flex items-center justify-center gap-1.5 min-h-[40px] px-4 rounded-xl bg-white/[0.03] border border-white/10 text-slate-300 hover:text-white hover:bg-white/[0.06] disabled:opacity-40 disabled:cursor-not-allowed text-xs font-bold transition-all"
                  >
                    <Save size={12} />
                    {t('compose.save_as_template')}
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
                        {t('compose.deleting')}
                      </>
                    ) : (
                      <>
                        <Trash2 size={12} />
                        {t('compose.delete_template')}
                      </>
                    )}
                  </button>
                </div>

                {showSaveTemplateForm && (
                  <div className="space-y-2 rounded-xl border border-white/[0.06] bg-black/5 px-3 py-2.5">
                    <label htmlFor="reply-template-name-input" className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      {t('compose.template_name')}
                    </label>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input
                        id="reply-template-name-input"
                        name="templateName"
                        type="text"
                        value={templateName}
                        onChange={(e) => setTemplateName(e.target.value)}
                        placeholder={t('compose.template_name_placeholder')}
                        disabled={templateSaving}
                        className="flex-1 px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 disabled:opacity-50 transition-all"
                      />
                      <button
                        onClick={handleSaveTemplate}
                        disabled={!canSubmitTemplateSave}
                        className="inline-flex items-center justify-center gap-1.5 min-h-[40px] px-4 rounded-xl bg-primary-600 hover:bg-primary-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold transition-all"
                      >
                        {templateSaving ? (
                          <>
                            <RefreshCw size={12} className="animate-spin" />
                            {t('compose.saving')}
                          </>
                        ) : (
                          <>
                            <Save size={12} />
                            {t('compose.save')}
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <ThreadContextSignal result={threadContext} />

              <div className="rounded-2xl border border-primary-500/[0.14] bg-white/[0.035] px-3 py-3 sm:px-4 sm:py-4 space-y-2 shadow-lg shadow-black/10 transition-colors duration-150 focus-within:border-primary-500/[0.26] focus-within:bg-white/[0.05]">
                <div className="space-y-1">
                  <p id="reply-body-label" className="text-[10px] font-black text-primary-300 uppercase tracking-[0.2em]">
                    {t('compose.reply_body')}
                  </p>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {t('compose.reply_body_help')}
                  </p>
                </div>

                <textarea
                  id="reply-body-textarea"
                  name="replyBody"
                  aria-labelledby="reply-body-label"
                  ref={replyTextareaRef}
                  value={replyBody}
                  onChange={(e) => onReplyBodyChange(e.target.value)}
                  placeholder={t('compose.reply_body_placeholder')}
                  rows={6}
                  className="w-full min-h-[220px] resize-none bg-transparent border-0 p-0 text-sm leading-relaxed text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-0"
                />
              </div>

              {/* —— Reference context —— read-only, never included in outbound body —— */}
              {hasReference && (
                <div className="border-t border-white/[0.06] pt-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.18em] select-none">
                      {t('compose.reference_not_sent')}
                    </p>
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em]">
                      {t('compose.tone_value', { tone: (() => { const found = toneOptions.find((tone) => tone.code === effectiveTone); return found ? getToneDisplayLabel(found) : effectiveTone; })() })}
                    </span>
                  </div>

                  {/* AI summary + action items — always visible when present */}
                  {hasAiSummary && (
                    <div className="space-y-2">
                      <AiSummaryConfidence email={email} />

                      <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-white/[0.025] border border-white/[0.06]">
                        <Sparkles size={10} className="text-primary-300 mt-0.5 flex-shrink-0" />
                        <p className="text-xs text-slate-300/85 leading-relaxed">
                          {email.ai_summary_text}
                        </p>
                      </div>

                      {email.ai_summary_json?.action_items && email.ai_summary_json.action_items.length > 0 && (
                        <div className="px-3 py-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05] space-y-1.5">
                          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.14em]">
                            {t('compose.action_items')}
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
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-white/[0.08] bg-white/[0.03] text-[10px] font-semibold text-slate-300 hover:text-white hover:bg-white/[0.05] transition-colors"
                          aria-expanded={showQuoted}
                        >
                          <ChevronDown
                            size={11}
                            className={`transition-transform duration-150 ${showQuoted ? 'rotate-180' : ''}`}
                          />
                          {showQuoted ? t('compose.hide_original') : t('compose.show_original')}
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

            {/* Attachment list — flex-shrink-0 sibling, visually directly above the footer */}
            {(attachmentError != null || attachments.length > 0) && (
              <div className="flex-shrink-0 border-t border-white/[0.06] bg-brand-surface px-4 py-3 sm:px-6 space-y-2">
                {attachmentError && (
                  <div
                    role="alert"
                    aria-live="assertive"
                    className="flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs"
                  >
                    <AlertCircle size={13} className="flex-shrink-0" />
                    <span className="font-bold">{attachmentError}</span>
                  </div>
                )}

                {attachments.length > 0 && (
                  <ul
                    className="rounded-xl border border-white/[0.06] bg-white/[0.02] divide-y divide-white/[0.04]"
                    aria-label={t('compose.attachments_list')}
                  >
                    {attachments.map((att, idx) => (
                      <li key={idx} className="flex items-center justify-between gap-2 px-3 py-2">
                        <div className="min-w-0 flex-1">
                          <p className="text-xs text-slate-200 truncate">{att.filename}</p>
                          <p className="text-[10px] text-slate-500">{formatBytes(att.size)}</p>
                        </div>
                        <button
                          type="button"
                          aria-label={t('compose.remove_attachment', { filename: att.filename })}
                          onClick={() => onRemoveAttachment?.(idx)}
                          className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] sm:min-h-[32px] sm:min-w-[32px] rounded-lg hover:bg-white/10 text-slate-400 hover:text-rose-400 transition-colors flex-shrink-0"
                        >
                          <X size={14} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {attachments.length > 0 && (
                  <p className="text-[10px] text-slate-500 px-1">
                    {t('compose.total_attachment_size', { size: formatBytes(attachmentsTotalBytes) })}
                  </p>
                )}

                <p className="text-[10px] text-slate-600 px-1">
                  {t('compose.attachment_privacy_notice')}
                </p>
              </div>
            )}

            {/* Footer — action bar
                Mobile: flex-col-reverse stacks Send on top (full-width) and Discard below.
                sm+: flex-row with Discard left, Attach+Send cluster right — standard desktop pattern. */}
            <div className="flex-shrink-0 border-t border-white/[0.12] bg-brand-surface px-4 py-3 sm:px-6 sm:py-4 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-2.5 sm:gap-3">
              {/* Hidden file input — triggered via htmlFor on the label below */}
              <input
                id="reply-attachment-input"
                name="replyAttachments"
                type="file"
                multiple
                aria-label={t('compose.attach')}
                className="sr-only"
                disabled={attachmentsDisabled}
                onChange={(e) => {
                  const files = e.target.files;
                  if (onAddAttachments && files && files.length > 0) {
                    onAddAttachments(Array.from(files));
                  }
                  e.target.value = '';
                }}
              />
              <button
                onClick={onDiscard}
                disabled={sending}
                className="w-full sm:w-auto inline-flex items-center justify-center min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-400 hover:text-white text-xs font-bold transition-all"
              >
                {t('compose.discard')}
              </button>
              <div className="flex flex-col-reverse sm:flex-row sm:items-center gap-2 sm:gap-3 w-full sm:w-auto">
                <label
                  htmlFor="reply-attachment-input"
                  aria-disabled={attachmentsDisabled}
                  className={`w-full sm:w-auto inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl border text-xs font-bold transition-all select-none ${
                    attachmentsDisabled
                      ? 'bg-white/[0.02] border-white/[0.05] text-slate-600 opacity-50 cursor-not-allowed pointer-events-none'
                      : 'bg-white/[0.04] border-white/10 text-slate-300 hover:text-white hover:bg-white/[0.08] cursor-pointer'
                  }`}
                >
                  <Paperclip size={12} />
                  {t('compose.attach')}
                </label>
                <button
                  onClick={onSend}
                  disabled={sending || !replyBody.trim() || !email.thread_id}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition-all shadow-lg shadow-primary-600/20"
                >
                  {sending ? (
                    <>
                      <RefreshCw size={12} className="animate-spin" />
                      {t('compose.sending')}
                    </>
                  ) : (
                    <>
                      <Mail size={12} />
                      {t('compose.send_reply')}
                    </>
                  )}
                </button>
              </div>
            </div>
          </motion.div>
        </FocusTrap>
      </div>
    </>
  );
}
