import { RefObject } from 'react';
import { Sparkles, Bot } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Briefing } from '@types';
import { normalizeBodyText } from '@utils/normalizeBodyText';

interface Props {
  email: Briefing;
  actionItemsRef: RefObject<HTMLDivElement>;
  onReadFull: () => void;
  isSummarizing?: boolean;
  /** Opens the AI Assistant panel for this email. */
  onAskAssistant?: () => void;
}

/**
 * Quick View
 *
 * Inbox:
 *   - Shows AI analysis, urgency, action items, and assistant entry point.
 * Sent:
 *   - Suppresses AI-analysis framing and instead shows a lightweight outbound preview.
 *
 * All action buttons live in EmailDetailModal's footer.
 */
export function EmailQuickView({ email, actionItemsRef, onReadFull, isSummarizing, onAskAssistant }: Props) {
  const { t } = useTranslation();

  const getUrgencyLabel = (urgency: string) => {
    const normalized = urgency.toLowerCase();
    if (normalized === 'high') return t('inbox.urgency.high');
    if (normalized === 'low') return t('inbox.urgency.low');
    return t('inbox.urgency.medium');
  };

  const isSent = Boolean(email.sentMeta);

  const rawText = isSent
    ? (email.sentMeta?.bodyPreview || email.body || email.summary || '')
    : (email.body || email.summary || '');

  const bodyText = normalizeBodyText(rawText);
  const preview = bodyText.length > 320 ? `${bodyText.slice(0, 320)}...` : bodyText;
  const showInlineReadFullCta = isSent;
  const showCardReadFullCta = !isSent && bodyText.length > 320;

  const urgencyRaw = email.ai_summary_json?.urgency;
  const normalizedUrgency = typeof urgencyRaw === 'string' ? urgencyRaw.trim().toLowerCase() : '';

  const aiAnalysisCardClassName = (() => {
    const base = 'p-4 rounded-2xl border border-white/5 bg-white/[0.03]';

    if (normalizedUrgency === 'high') {
      return `${base} border-l-[4px] border-l-[#DC2626] bg-[rgba(220,38,38,0.04)]`;
    }

    if (normalizedUrgency === 'medium') {
      return `${base} border-l-[4px] border-l-[#D97706] bg-[rgba(217,119,6,0.04)]`;
    }

    if (normalizedUrgency === 'low') {
      return `${base} border-l-[4px] border-l-[#059669] bg-[rgba(5,150,105,0.04)]`;
    }

    return base;
  })();

  const urgencyTextClassName = (() => {
    if (normalizedUrgency === 'high') {
      return 'text-[#DC2626]';
    }

    if (normalizedUrgency === 'medium') {
      return 'text-[#D97706]';
    }

    if (normalizedUrgency === 'low') {
      return 'text-[#059669]';
    }

    return 'text-slate-500';
  })();

  return (
    <div className="space-y-6">
      {!isSent && !email.ai_summary_text && isSummarizing && (
        /* Skeleton — summarization actively in progress */
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-primary-400 animate-pulse" />
            <h3 className="text-sm font-semibold text-primary-400 uppercase tracking-wider">{t('modal.ai_analysis')}</h3>
          </div>
          <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 space-y-2.5">
            <div className="skeleton-bar h-3.5" style={{ width: '90%' }} />
            <div className="skeleton-bar h-3.5" style={{ width: '60%' }} />
          </div>
        </div>
      )}

      {!isSent && !email.ai_summary_text && !isSummarizing && (
        /* Placeholder — auto-summarization queued, result arriving shortly */
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-slate-600" />
            <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">{t('modal.ai_analysis')}</h3>
          </div>
          <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <p className="text-xs text-slate-500 leading-relaxed">
              {t('modal.summary_generating')}
            </p>
          </div>
        </div>
      )}

      {!isSent && email.ai_summary_text && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-primary-400" />
            <h3 className="text-sm font-semibold text-primary-400 uppercase tracking-wider">{t('modal.ai_analysis')}</h3>
            {email.ai_summary_model && (
              <span className="text-[9px] text-slate-600 font-bold">{email.ai_summary_model}</span>
            )}
          </div>

          <div className={aiAnalysisCardClassName}>
            <p className="text-sm leading-relaxed text-slate-200">{email.ai_summary_text}</p>

            {email.ai_summary_json?.urgency && (
              <p className={`mt-3 text-xs font-semibold ${urgencyTextClassName}`}>
                {t('modal.urgency_label')}{' '}
                <span className={`font-bold capitalize ${urgencyTextClassName}`}>
                  {getUrgencyLabel(email.ai_summary_json.urgency)}
                </span>
              </p>
            )}
          </div>

          {email.ai_summary_json?.action_items && email.ai_summary_json.action_items.length > 0 && (
            <div ref={actionItemsRef} className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
              <p className="text-xs font-semibold text-primary-400 uppercase tracking-wider mb-3">{t('modal.action_items')}</p>
              <ol className="space-y-2 list-decimal list-inside">
                {email.ai_summary_json.action_items.map((action: string, idx: number) => (
                  <li key={idx} className="text-sm leading-relaxed text-slate-300">{action}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      <div className="space-y-3">
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
              {isSent ? t('modal.outbound_preview') : t('modal.preview')}
            </h3>

            {showInlineReadFullCta && (
              <button
                type="button"
                onClick={onReadFull}
                className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[11px] font-bold text-primary-400 hover:text-primary-300 hover:border-primary-500/30 hover:bg-primary-500/[0.08] transition-all"
              >
                {t('modal.read_full_email')}
              </button>
            )}
          </div>

          {isSent && (
            <p className="text-xs leading-relaxed text-slate-500">
              {t('modal.sent_preview_notice')}
            </p>
          )}
        </div>

        <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
          <p className="text-sm leading-relaxed text-slate-300 whitespace-pre-wrap break-words">
            {preview || (isSent ? t('modal.no_outbound_preview') : t('modal.no_preview'))}
          </p>
          {showCardReadFullCta && (
            <button
              type="button"
              onClick={onReadFull}
              className="mt-3 text-xs font-bold text-primary-400 hover:text-primary-300 transition-colors"
            >
              {t('modal.read_full_email')}
            </button>
          )}
        </div>
      </div>


      {!isSent && onAskAssistant && (
        <button
          onClick={onAskAssistant}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-2xl bg-white/[0.03] border border-white/[0.08] hover:bg-primary-500/[0.08] hover:border-primary-500/30 text-slate-400 hover:text-primary-300 text-xs font-semibold transition-all"
        >
          <Bot size={13} />
          {t('modal.ask_ai_assistant')}
        </button>
      )}
    </div>
  );
}
