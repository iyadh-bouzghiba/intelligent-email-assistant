import { useTranslation } from 'react-i18next';
import { Paperclip, Clock } from 'lucide-react';
import type { SpineSignalResult } from '@utils/deriveSpineSignals';

export interface ThreadSpineProps {
  result: SpineSignalResult;
  className?: string;
}

export function ThreadSpine({ result, className }: ThreadSpineProps) {
  const { t } = useTranslation();

  if (!result.hasAnySignal) return null;

  let recencyLabel: string | null = null;
  let recencyClass: string | null = null;
  if (result.daysSinceLastActivity !== null) {
    if (result.isPendingReply === true && result.daysSinceLastActivity >= 1) {
      recencyLabel = t('spine.reply_pending', { count: result.daysSinceLastActivity });
      recencyClass = 'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border text-blue-400 border-blue-500/40 bg-blue-500/10';
    } else if (result.daysSinceLastActivity === 0) {
      recencyLabel = t('spine.recency_today');
      recencyClass = 'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border text-slate-400 border-slate-500/40 bg-slate-500/10';
    } else {
      recencyLabel = t('spine.recency_days', { count: result.daysSinceLastActivity });
      recencyClass = 'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border text-slate-400 border-slate-500/40 bg-slate-500/10';
    }
  }

  return (
    <div
      role="group"
      aria-label={t('spine.thread_context')}
      className={`flex flex-wrap gap-1 mt-1 mb-2${className ? ` ${className}` : ''}`}
      dir="auto"
    >
      {result.urgencyLevel === 'high' && (() => {
        const label = t('spine.urgency_high');
        return (
          <span
            role="img"
            aria-label={label}
            title={label}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border text-amber-400 border-amber-500/40 bg-amber-500/10"
          >
            {label}
          </span>
        );
      })()}

      {result.urgencyLevel === 'medium' && (() => {
        const label = t('spine.urgency_medium');
        return (
          <span
            role="img"
            aria-label={label}
            title={label}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border text-blue-400 border-blue-500/40 bg-blue-500/10"
          >
            {label}
          </span>
        );
      })()}

      {result.hasAttachments === true && (() => {
        const label = t('spine.has_attachments');
        return (
          <span
            role="img"
            aria-label={label}
            title={label}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
          >
            <Paperclip size={9} aria-hidden />
            {label}
          </span>
        );
      })()}

      {recencyLabel !== null && recencyClass !== null && (
        <span
          role="img"
          aria-label={recencyLabel}
          title={recencyLabel}
          className={recencyClass}
        >
          <Clock size={9} aria-hidden />
          {recencyLabel}
        </span>
      )}

      {result.threadDepth !== null && (() => {
        const label = t('spine.thread_depth', { count: result.threadDepth });
        return (
          <span
            role="img"
            aria-label={label}
            title={label}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border text-slate-400 border-slate-600/40 bg-slate-700/30"
          >
            {label}
          </span>
        );
      })()}
    </div>
  );
}
