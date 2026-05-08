import { motion } from 'framer-motion';
import { X, MailOpen, Mail, RefreshCw } from 'lucide-react';
import { AILanguage, Briefing } from '@types';
import { apiService } from '../services/api';
import { FocusTrap } from './FocusTrap';
import { EmailQuickView } from './EmailQuickView';
import { EmailFullView } from './EmailFullView';
import { RefObject, useEffect, useState } from 'react';

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
  onGeneratePreferred: () => void | Promise<void>;
  onMarkRead: () => void;
  onMarkUnread: () => void;
  onAskAssistant?: () => void;
  getCategoryStyles: (cat: string) => string;
  preferredLanguage: string;
}

interface RenderedEmailTextPayload {
  body_text?: string | null;
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
  onGeneratePreferred,
  onMarkRead,
  onMarkUnread,
  onAskAssistant,
  getCategoryStyles,
  preferredLanguage,
}: Props) {
  const languageLabel = (code?: string | null) => {
    if (code === 'fr') return 'French';
    if (code === 'ar') return 'Arabic';
    return 'English';
  };

  const actualSummaryLanguage = email.ai_summary_language ?? 'en';
  const effectivePreferredLanguage = email.ai_preferred_language ?? preferredLanguage ?? 'en';

  const showPreferredLanguageMismatch = Boolean(
    email.ai_summary_text &&
    email.ai_summary_is_fallback &&
    !email.ai_preferred_language_available
  );

  const summarizeButtonQueued = Boolean(isSummarizing);

  const summarizeButtonIdleLabel = showPreferredLanguageMismatch
    ? `Generate ${languageLabel(effectivePreferredLanguage)} version`
    : 'Refresh AI Summary';

  const summarizeButtonHandler = showPreferredLanguageMismatch
    ? onGeneratePreferred
    : onSummarize;

  const sentMeta = detailIsSent ? email.sentMeta : undefined;

  const sentAtDisplay = (() => {
    if (!sentMeta?.sentAt) return email.date;
    try {
      return new Date(sentMeta.sentAt).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
    } catch {
      return sentMeta.sentAt;
    }
  })();

  const showPreferredLanguageBanner = !detailIsSent && showPreferredLanguageMismatch;
  const showSummarizeButton = !detailIsSent && Boolean(email.ai_summary_text && email.gmail_message_id);

  const emailIdentity = email.gmail_message_id ?? email.thread_id ?? `${email.subject}|${email.date}`;
  const fallbackTranslationBody = detailIsSent
    ? (sentMeta?.bodyPreview || email.body || email.summary || '')
    : (email.body || email.summary || '');

  const normalizedTranslationLanguage: AILanguage =
    effectivePreferredLanguage === 'fr' || effectivePreferredLanguage === 'ar'
      ? effectivePreferredLanguage
      : 'en';

  const showTranslateButton = Boolean((fallbackTranslationBody || '').trim() || email.gmail_message_id);

  const [translationPending, setTranslationPending] = useState(false);
  const [translationActive, setTranslationActive] = useState(false);
  const [translatedBody, setTranslatedBody] = useState<string | null>(null);
  const [translationError, setTranslationError] = useState<string | null>(null);
  const [translationTargetLanguage, setTranslationTargetLanguage] = useState<AILanguage | null>(null);

  useEffect(() => {
    setTranslationPending(false);
    setTranslationActive(false);
    setTranslatedBody(null);
    setTranslationError(null);
    setTranslationTargetLanguage(null);
  }, [emailIdentity, normalizedTranslationLanguage]);

  const resolveTranslationSourceBody = async (): Promise<string> => {
    if (email.gmail_message_id) {
      try {
        const response = await fetch(`/api/emails/${encodeURIComponent(email.gmail_message_id)}/rendered`, {
          credentials: 'include',
        });

        if (response.ok) {
          const payload = (await response.json()) as RenderedEmailTextPayload;
          const renderedBodyText = (payload.body_text || '').trim();
          if (renderedBodyText) {
            return renderedBodyText;
          }
        }
      } catch {
        // Fall through to local body fallback.
      }
    }

    return fallbackTranslationBody;
  };

  const handleTranslateToggle = async () => {
    if (translationPending) return;

    if (translationActive) {
      setTranslationActive(false);
      setTranslationError(null);
      return;
    }

    if (translatedBody && translationTargetLanguage === normalizedTranslationLanguage) {
      if (panelView === 'quick') {
        onSwitchView('full');
      }
      setTranslationError(null);
      setTranslationActive(true);
      return;
    }

    if (panelView === 'quick') {
      onSwitchView('full');
    }

    setTranslationPending(true);
    setTranslationError(null);

    try {
      const sourceBody = await resolveTranslationSourceBody();
      if (!sourceBody.trim()) {
        setTranslatedBody(null);
        setTranslationTargetLanguage(null);
        setTranslationActive(false);
        setTranslationError('No translatable body available for this email.');
        return;
      }

      const result = await apiService.translateEmailBody(sourceBody, normalizedTranslationLanguage);
      if (result.error) {
        setTranslatedBody(null);
        setTranslationTargetLanguage(null);
        setTranslationActive(false);
        setTranslationError(result.error);
        return;
      }

      const translated = (result.translated_body || '').trim();
      if (!translated) {
        setTranslatedBody(null);
        setTranslationTargetLanguage(null);
        setTranslationActive(false);
        setTranslationError('Translation returned empty content.');
        return;
      }

      setTranslatedBody(translated);
      setTranslationTargetLanguage(normalizedTranslationLanguage);
      setTranslationActive(true);
    } catch {
      setTranslatedBody(null);
      setTranslationTargetLanguage(null);
      setTranslationActive(false);
      setTranslationError('Translation failed. Please try again.');
    } finally {
      setTranslationPending(false);
    }
  };

  const translateInlineState: 'idle' | 'loading' | 'translated' | 'error' =
    translationPending
      ? 'loading'
      : translationActive
        ? 'translated'
        : translationError
          ? 'error'
          : 'idle';

  const showInboxFooter = !detailIsSent;

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
            className="pointer-events-auto w-full h-full sm:h-auto sm:max-h-[90vh] sm:max-w-2xl bg-brand-surface border-0 sm:border sm:border-brand-border rounded-none sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex-shrink-0 bg-brand-surface border-b border-white/5 px-4 py-4 sm:px-6 sm:py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h2 id={TITLE_ID} className="text-xl font-black text-white mb-2 leading-tight">
                    {email.subject}
                  </h2>

                  <div id={DESC_ID} className="flex flex-col gap-2 text-sm text-slate-400">
                    {detailIsSent ? (
                      <>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-600">To</span>
                          <span className="font-semibold text-slate-200 break-all">
                            {sentMeta?.toAddress || 'Unknown recipient'}
                          </span>
                        </div>

                        {sentMeta?.ccAddresses && (
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-600">CC</span>
                            <span className="text-slate-300 break-all">{sentMeta.ccAddresses}</span>
                          </div>
                        )}

                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-600">Sent at</span>
                          <span>{sentAtDisplay}</span>
                        </div>
                      </>
                    ) : (
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-slate-300">{email.sender}</span>
                        <span className="text-slate-600">|</span>
                        <span>{email.date}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 mt-3">
                    {detailIsSent ? (
                      <span className="px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border bg-slate-500/10 text-slate-400 border-slate-500/20">
                        Sent
                      </span>
                    ) : (
                      <>
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${email.priority === 'High'
                              ? 'bg-[#FF3B5C] text-white border-[#FF3B5C]'
                              : email.priority === 'Medium'
                                ? 'bg-[#FFB800] text-[#1a1a1a] border-[#FFB800]'
                                : 'bg-[#3D4A5C] text-[#94A3B8] border-[#3D4A5C]'
                            }`}
                        >
                          {email.priority}
                        </span>

                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${getCategoryStyles(email.category)}`}
                        >
                          {email.category}
                        </span>

                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${isRead
                              ? 'bg-slate-500/10 text-slate-500 border-slate-500/20'
                              : 'bg-primary-500/10 text-primary-400 border-primary-500/20'
                            }`}
                        >
                          {isRead ? 'Read' : 'Unread'}
                        </span>
                      </>
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

            {/* Scrollable body */}
            <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-6 space-y-8 min-h-0 sm:px-8 sm:py-8">
              {showPreferredLanguageBanner && (
                <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-amber-300">
                    Preferred language version not generated yet
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-amber-100/90">
                    The saved summary currently shown is in{' '}
                    <span className="font-semibold">{languageLabel(actualSummaryLanguage)}</span>.
                    {' '}Your preferred language is{' '}
                    <span className="font-semibold">{languageLabel(effectivePreferredLanguage)}</span>.
                    {' '}Generate the preferred-language version to replace this fallback view.
                  </p>
                </div>
              )}

              {panelView === 'quick' ? (
                <EmailQuickView
                  email={email}
                  actionItemsRef={actionItemsRef}
                  onReadFull={() => onSwitchView('full')}
                  isSummarizing={isSummarizing}
                  onAskAssistant={onAskAssistant}
                />
              ) : (
                <EmailFullView
                  email={email}
                  actionItemsRef={actionItemsRef}
                  onBackToSummary={() => onSwitchView('quick')}
                  translationActive={translationActive}
                  translatedBody={translatedBody}
                  translationTargetLanguage={translationTargetLanguage}
                  translationError={translationError}
                  showRefreshSummary={showSummarizeButton}
                  onRefreshSummary={summarizeButtonHandler}
                  refreshSummaryQueued={summarizeButtonQueued}
                  refreshSummaryTitle={summarizeButtonIdleLabel}
                  showTranslateControls={showTranslateButton}
                  translateState={translateInlineState}
                  translateLanguageLabel={languageLabel(normalizedTranslationLanguage)}
                  onTranslateToggle={handleTranslateToggle}
                />
              )}
            </div>

            {showInboxFooter && (
              <div className="flex-shrink-0 border-t border-white/[0.12] bg-brand-surface px-4 py-3 sm:px-6 sm:py-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center">
                    {modifyScope && (
                      isRead ? (
                        <button
                          onClick={onMarkUnread}
                          disabled={readStatePending}
                          title="Mark as unread"
                          className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-300 hover:text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {readStatePending ? <RefreshCw size={12} className="animate-spin" /> : <Mail size={12} />}
                          Mark Unread
                        </button>
                      ) : (
                        <button
                          onClick={onMarkRead}
                          disabled={readStatePending}
                          title="Mark as read"
                          className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-300 hover:text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {readStatePending ? <RefreshCw size={12} className="animate-spin" /> : <MailOpen size={12} />}
                          Mark Read
                        </button>
                      )
                    )}
                  </div>

                  <div className="flex items-center justify-end">
                    <button
                      onClick={onOpenReply}
                      className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-5 rounded-xl bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white text-xs font-bold transition-all shadow-lg shadow-primary-600/20"
                    >
                      <Mail size={12} />
                      Draft Reply
                    </button>
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        </FocusTrap>
      </div>
    </>
  );
}
