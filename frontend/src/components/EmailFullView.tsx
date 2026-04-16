import { RefObject } from 'react';
import { Sparkles } from 'lucide-react';
import { Briefing } from '@types';

interface Props {
  email: Briefing;
  actionItemsRef: RefObject<HTMLDivElement>;
  onBackToSummary: () => void;
}

/**
 * Full View — shows AI summary (if present) and the complete message body.
 * All action buttons live in EmailDetailModal's footer.
 */
export function EmailFullView({ email, actionItemsRef, onBackToSummary }: Props) {
  return (
    <div className="space-y-6">
      {/* AI Analysis — mirrored from Quick View so context is preserved */}
      {email.ai_summary_text && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-indigo-400" />
            <h3 className="text-sm font-semibold text-indigo-400 uppercase tracking-wider">AI Analysis</h3>
            {email.ai_summary_model && (
              <span className="text-[9px] text-slate-600 font-bold">{email.ai_summary_model}</span>
            )}
          </div>

          <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
            <p className="text-sm leading-relaxed text-slate-200">{email.ai_summary_text}</p>
          </div>

          {email.ai_summary_json?.action_items && email.ai_summary_json.action_items.length > 0 && (
            <div ref={actionItemsRef} className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
              <p className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-3">Action Items</p>
              <ol className="space-y-2 list-decimal list-inside">
                {email.ai_summary_json.action_items.map((action: string, idx: number) => (
                  <li key={idx} className="text-sm leading-relaxed text-slate-300">{action}</li>
                ))}
              </ol>
            </div>
          )}

          {email.ai_summary_json?.urgency && (
            <p className="text-xs text-slate-500">
              Urgency:{' '}
              <span className="font-bold text-slate-400 capitalize">{email.ai_summary_json.urgency}</span>
            </p>
          )}
        </div>
      )}

      {/* Full Message */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Full Message</h3>
          <button
            onClick={onBackToSummary}
            className="text-[10px] font-bold text-slate-600 hover:text-slate-400 transition-colors"
          >
            ← Summary
          </button>
        </div>
        <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
          <pre className="text-sm leading-relaxed text-slate-300 whitespace-pre-wrap font-sans break-words">
            {email.body || email.summary || 'No message body available.'}
          </pre>
        </div>
      </div>
    </div>
  );
}
