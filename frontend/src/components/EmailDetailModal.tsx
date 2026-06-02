import { motion } from 'framer-motion';
import { X, MailOpen, Mail, RefreshCw } from 'lucide-react';
import { TranslationLanguage, EmailViewModel, TranslateRenderResponse } from '@types';
import { apiService } from '../services/api';
import { FocusTrap } from './FocusTrap';
import { EmailQuickView } from './EmailQuickView';
import { EmailFullView } from './EmailFullView';
import { RefObject, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  email: EmailViewModel;
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
  const { t, i18n } = useTranslation();

  const languageLabel = (code: string | null) => {
    switch (code) {
      case 'fr':
        return t('languages.french');
      case 'ar':
        return t('languages.arabic');
      case 'de':
        return t('languages.german');
      case 'es':
        return t('languages.spanish');
      case 'pt-BR':
        return t('languages.portuguese_brazil');
      case 'tr':
        return t('languages.turkish');
      case 'zh':
        return t('languages.chinese');
      case 'ja':
        return t('languages.japanese');
      case 'ko':
        return t('languages.korean');
      case 'en':
      default:
        return t('languages.english');
    }
  };

  const getPriorityDisplayLabel = (priority: string) => {
    const normalized = priority.toLowerCase();
    if (normalized === 'high') return t('inbox.urgency.high');
    if (normalized === 'low') return t('inbox.urgency.low');
    return t('inbox.urgency.medium');
  };

  const getCategoryDisplayLabel = (category: string) => {
    switch (category) {
      case 'Security': return t('inbox.categories.security');
      case 'Financial': return t('inbox.categories.financial');
      case 'Work': return t('inbox.categories.work');
      case 'Personal': return t('inbox.categories.personal');
      case 'Marketing': return t('inbox.categories.marketing');
      default: return t('inbox.categories.general');
    }
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
    ? t('modal.generate_language_version', { language: languageLabel(effectivePreferredLanguage) })
    : t('modal.refresh_ai_summary');

  const summarizeButtonHandler = showPreferredLanguageMismatch
    ? onGeneratePreferred
    : onSummarize;

  const dateLocale = i18n.resolvedLanguage ?? i18n.language ?? 'en';

  const formatDisplayDate = (value?: string | null, fallback = email.date) => {
    if (!value) return fallback;

    try {
      return new Date(value).toLocaleString(dateLocale, { dateStyle: 'medium', timeStyle: 'short' });
    } catch {
      return fallback;
    }
  };

  const sentMeta = detailIsSent ? email.sentMeta : undefined;

  const sentAtDisplay = formatDisplayDate(sentMeta?.sentAt, sentMeta?.sentAt ?? email.date);
  const receivedAtDisplay = formatDisplayDate(email.date_iso, email.date);

  const showPreferredLanguageBanner = !detailIsSent && showPreferredLanguageMismatch;
  const showSummarizeButton = !detailIsSent && Boolean(email.ai_summary_text && email.gmail_message_id);

  const emailIdentity = email.gmail_message_id ?? email.thread_id ?? `${email.subject}|${email.date}`;
  const fallbackTranslationBody = detailIsSent
    ? (sentMeta?.bodyPreview || email.body || email.summary || '')
    : (email.body || email.summary || '');

  const normalizedTranslationLanguage: TranslationLanguage =
    effectivePreferredLanguage === 'fr' || effectivePreferredLanguage === 'ar'
      ? effectivePreferredLanguage
      : 'en';

  const showTranslateButton = Boolean((fallbackTranslationBody || '').trim() || email.gmail_message_id);

  const [translationPending, setTranslationPending] = useState(false);
  const [translationActive, setTranslationActive] = useState(false);
  const [translatedBody, setTranslatedBody] = useState<string | null>(null);
  const [translatedBodyHtml, setTranslatedBodyHtml] = useState<string | null>(null);
  const [translationError, setTranslationError] = useState<string | null>(null);
  const [translationTargetLanguage, setTranslationTargetLanguage] = useState<TranslationLanguage | null>(null);
  const [translationMode, setTranslationMode] = useState<'structured_html' | 'text_fallback' | null>(null);
  const [translationFidelity, setTranslationFidelity] = useState<'preserved' | 'simplified' | null>(null);

  useEffect(() => {
    setTranslationPending(false);
    setTranslationActive(false);
    setTranslatedBody(null);
    setTranslatedBodyHtml(null);
    setTranslationError(null);
    setTranslationTargetLanguage(null);
    setTranslationMode(null);
    setTranslationFidelity(null);
  }, [emailIdentity, normalizedTranslationLanguage]);

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

    const resetOnError = (msg: string) => {
      setTranslatedBody(null);
      setTranslatedBodyHtml(null);
      setTranslationTargetLanguage(null);
      setTranslationActive(false);
      setTranslationError(msg);
      setTranslationMode(null);
      setTranslationFidelity(null);
    };

    try {
      if (email.gmail_message_id) {
        const result: TranslateRenderResponse = await apiService.translateRenderEmail(
          email.gmail_message_id,
          normalizedTranslationLanguage
        );
        if (result.error) {
          resetOnError(result.error);
          return;
        }
        const translated = (result.translated_body_text || '').trim();
        if (!translated) {
          resetOnError(t('modal.translation_returned_empty_content'));
          return;
        }
        setTranslatedBody(translated);
        setTranslatedBodyHtml(result.translated_body_html ?? null);
        setTranslationMode(result.translation_mode);
        setTranslationFidelity(result.translation_fidelity);
        setTranslationTargetLanguage(normalizedTranslationLanguage);
        setTranslationActive(true);
      } else {
        const sourceBody = fallbackTranslationBody.trim();
        if (!sourceBody) {
          resetOnError(t('modal.no_translatable_body_available'));
          return;
        }
        const result = await apiService.translateEmailBody(sourceBody, normalizedTranslationLanguage);
        if (result.error) {
          resetOnError(result.error);
          return;
        }
        const translated = (result.translated_body || '').trim();
        if (!translated) {
          resetOnError(t('modal.translation_returned_empty_content'));
          return;
        }
        setTranslatedBody(translated);
        setTranslatedBodyHtml(null);
        setTranslationTargetLanguage(normalizedTranslationLanguage);
        setTranslationActive(true);
      }
    } catch {
      resetOnError(t('modal.translation_failed_try_again'));
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
                          <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-600">{t('modal.to_label')}</span>
                          <span className="font-semibold text-slate-200 break-all">
                            {sentMeta?.toAddress || t('modal.unknown_recipient')}
                          </span>
                        </div>

                        {sentMeta?.ccAddresses && (
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-600">{t('modal.cc_label')}</span>
                            <span className="text-slate-300 break-all">{sentMeta.ccAddresses}</span>
                          </div>
                        )}

                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-600">{t('modal.sent_at')}</span>
                          <span>{sentAtDisplay}</span>
                        </div>
                      </>
                    ) : (
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-slate-300">{email.sender}</span>
                        <span className="text-slate-600">|</span>
                        <span>{receivedAtDisplay}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 mt-3">
                    {detailIsSent ? (
                      <span className="px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border bg-slate-500/10 text-slate-400 border-slate-500/20">
                        {t('modal.sent_badge')}
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
                          {getPriorityDisplayLabel(email.priority)}
                        </span>

                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${getCategoryStyles(email.category)}`}
                        >
                          {getCategoryDisplayLabel(email.category)}
                        </span>

                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${isRead
                            ? 'bg-slate-500/10 text-slate-500 border-slate-500/20'
                            : 'bg-primary-500/10 text-primary-400 border-primary-500/20'
                            }`}
                        >
                          {isRead ? t('common.read') : t('common.unread')}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                <button
                  data-modal-close
                  onClick={onClose}
                  aria-label={t('modal.close_email_details')}
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
                    {t('modal.preferred_language_version_not_generated_yet')}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-amber-100/90">
                    {t('modal.preferred_language_fallback_notice', {
                      actualLanguage: languageLabel(actualSummaryLanguage),
                      preferredLanguage: languageLabel(effectivePreferredLanguage),
                    })}
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
                  translatedBodyHtml={translatedBodyHtml}
                  translationMode={translationMode ?? undefined}
                  translationFidelity={translationFidelity ?? undefined}
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
                          title={t('modal.mark_as_unread')}
                          className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-300 hover:text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {readStatePending ? <RefreshCw size={12} className="animate-spin" /> : <Mail size={12} />}
                          {t('modal.mark_as_unread')}
                        </button>
                      ) : (
                        <button
                          onClick={onMarkRead}
                          disabled={readStatePending}
                          title={t('modal.mark_as_read')}
                          className="inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0 sm:py-2 px-4 rounded-xl bg-white/[0.05] border border-white/10 text-slate-300 hover:text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {readStatePending ? <RefreshCw size={12} className="animate-spin" /> : <MailOpen size={12} />}
                          {t('modal.mark_as_read')}
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
                      {t('modal.draft_reply')}
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
