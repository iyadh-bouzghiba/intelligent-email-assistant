import { Clock, Paperclip, Send, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SentEmail } from '@types';

// stripQuotedThread removes quoted reply chains from sent previews.
const stripQuotedThread = (preview: string | null): string => {
  if (!preview) return '';
  const text = preview.trim();
  const match = text.search(/\r?\nOn .{5,}\bwrote:/);
  if (match > 10) return text.substring(0, match).trim();
  return text;
};

interface Props {
  emails: SentEmail[];
  loading: boolean;
  onSelect: (email: SentEmail) => void;
}

const SENT_SKELETON_COUNT = 5;

function formatSentAt(sentAt: string, locale: string): string {
  try {
    return new Date(sentAt).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return sentAt;
  }
}

function compactText(value?: string | null): string {
  return (value || '').replace(/\s+/g, ' ').trim();
}

export function SentList({ emails, loading, onSelect }: Props) {
  const { t, i18n } = useTranslation();
  const dateLocale = i18n.resolvedLanguage ?? i18n.language ?? 'en';

  const cardLabel = (email: SentEmail): string => {
    const subject = compactText(email.subject) || t('sent.no_subject');
    const recipient = compactText(email.to_address) || t('sent.unknown_recipient');
    return t('sent.open_email_label', { subject, recipient });
  };

  if (loading) {
    return (
      <div className="flex flex-col gap-4" aria-label={t('sent.loading')}>
        {[...Array(SENT_SKELETON_COUNT)].map((_, i) => (
          <div
            key={i}
            className="rounded-2xl bg-white/[0.025] border border-white/[0.07] p-4 sm:p-5 flex flex-col gap-4 relative overflow-hidden shadow-xl"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="w-24 h-5 rounded-full bg-white/5 animate-pulse" />
              <div className="w-28 h-3 rounded-lg bg-white/5 animate-pulse" />
            </div>
            <div className="w-4/5 h-5 rounded-lg bg-white/5 animate-pulse" />
            <div className="space-y-2">
              <div className="w-full h-3 rounded-lg bg-white/5 animate-pulse" />
              <div className="w-2/3 h-3 rounded-lg bg-white/5 animate-pulse" />
            </div>
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.018] to-transparent -translate-x-full animate-[shimmer_2s_infinite]" />
          </div>
        ))}
      </div>
    );
  }

  if (emails.length === 0) {
    return (
      <div className="w-full py-28 sm:py-32 flex flex-col items-center gap-6 text-center">
        <div className="w-24 h-24 rounded-full bg-primary-500/[0.08] flex items-center justify-center text-primary-300 border border-primary-400/15 relative shadow-inner">
          <Send size={38} className="text-primary-300/45" />
        </div>
        <div className="max-w-sm">
          <h3 className="text-xl font-black text-white mb-2">{t('sent.empty_title')}</h3>
          <p className="text-slate-400 text-sm leading-relaxed font-medium">
            {t('sent.empty_description')}
          </p>
          <p className="text-slate-600 text-xs mt-3 leading-relaxed">
            {t('sent.empty_scope_notice')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {emails.map((email) => {
        const subject = compactText(email.subject) || t('sent.no_subject');
        const preview = compactText(stripQuotedThread(email.body_preview));
        const toAddress = compactText(email.to_address) || t('sent.unknown_recipient');
        const ccAddresses = compactText(email.cc_addresses);

        return (
          <button
            type="button"
            aria-label={cardLabel(email)}
            onClick={() => onSelect(email)}
            className="group text-left w-full rounded-2xl bg-white/[0.025] border border-white/[0.07] hover:bg-white/[0.045] hover:border-primary-400/25 transition-all duration-200 shadow-xl overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400/70"
          >
            <div className="p-4 sm:p-5 flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3 min-w-0">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-wider border bg-primary-500/10 text-primary-300 border-primary-400/20 flex-shrink-0">
                    <Send size={10} />
                    {t('sent.badge_sent')}
                  </span>
                  <span className="text-[10px] font-black text-slate-600 uppercase tracking-[0.18em] flex-shrink-0">
                    {t('sent.to_label')}
                  </span>
                  <span className="text-xs font-semibold text-slate-300 truncate">
                    {toAddress}
                  </span>
                </div>

                <div className="flex items-center gap-1.5 text-[10px] text-slate-600 flex-shrink-0 pt-0.5">
                  <Clock size={11} className="text-primary-400/55" />
                  <span>{formatSentAt(email.sent_at, dateLocale)}</span>
                </div>
              </div>

              {ccAddresses && (
                <div className="flex items-center gap-2 min-w-0 text-[11px] text-slate-500">
                  <Users size={12} className="text-slate-600 flex-shrink-0" />
                  <span className="font-bold uppercase tracking-wider text-slate-600 flex-shrink-0">{t('sent.cc_label')}</span>
                  <span className="truncate">{ccAddresses}</span>
                </div>
              )}

              <div className="min-w-0">
                <h3 className="text-base sm:text-[17px] font-black text-white group-hover:text-primary-300 transition-colors leading-snug truncate">
                  {subject}
                  {email.has_attachments && (
                    <span role="img" aria-label={t('inbox.has_attachments')} title={t('inbox.has_attachments')} className="inline-block">
                      <Paperclip size={13} className="inline-block ml-1.5 text-slate-400 align-[-1px]" aria-hidden="true" />
                    </span>
                  )}
                </h3>

                {preview ? (
                  <p className="mt-2 text-sm text-slate-400 leading-relaxed line-clamp-2 break-words">
                    {preview}
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-slate-600 italic">
                    {t('sent.no_preview')}
                  </p>
                )}
              </div>

              <div className="pt-1 flex items-center justify-end gap-3">
                <span className="text-[10px] font-black uppercase tracking-[0.18em] text-primary-500/80 opacity-0 group-hover:opacity-100 transition-opacity">
                  {t('sent.open')}
                </span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
