import React from 'react';
import { Paperclip } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ThreadContextResult } from '@utils/deriveThreadContext';

interface Props {
  result: ThreadContextResult;
  className?: string;
}

const urgencyChipClass: Record<string, string> = {
  high: 'bg-amber-500/10 border border-amber-500/25 text-amber-300',
  medium: 'bg-blue-500/10 border border-blue-500/20 text-blue-300',
};

export default function ThreadContextSignal({ result, className }: Props) {
  const { t } = useTranslation();

  const showUrgency = result.urgencyLevel === 'high' || result.urgencyLevel === 'medium';
  const showAttachments = result.threadHasAttachments === true;
  const showDepth = typeof result.threadDepth === 'number' && result.threadDepth >= 3;

  if (!showUrgency && !showAttachments && !showDepth) {
    return null;
  }

  return (
    <div
      role="group"
      aria-label={t('compose.context.strip_aria_label')}
      className={`flex flex-wrap gap-1.5${className ? ` ${className}` : ''}`}
    >
      {showUrgency && (
        <span
          aria-label={t(
            result.urgencyLevel === 'high'
              ? 'compose.context.urgency_high_aria'
              : 'compose.context.urgency_medium_aria'
          )}
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${urgencyChipClass[result.urgencyLevel]}`}
        >
          {t(
            result.urgencyLevel === 'high'
              ? 'compose.context.urgency_high'
              : 'compose.context.urgency_medium'
          )}
        </span>
      )}

      {showAttachments && (
        <span
          aria-label={t('compose.context.has_attachments_aria')}
          className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-white/[0.04] border border-white/10 text-slate-300"
        >
          <Paperclip size={11} className="opacity-70" />
          {t('compose.context.has_attachments')}
        </span>
      )}

      {showDepth && (
        <span
          aria-label={t('compose.context.thread_depth_aria', { count: result.threadDepth })}
          className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-white/[0.04] border border-white/10 text-slate-400"
        >
          {t('compose.context.thread_depth', { count: result.threadDepth })}
        </span>
      )}
    </div>
  );
}
