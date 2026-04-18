import { RefObject } from 'react';
import { Sparkles } from 'lucide-react';
import { Briefing } from '@types';
import { normalizeBodyText } from '@utils/normalizeBodyText';

interface Props {
  email: Briefing;
  actionItemsRef: RefObject<HTMLDivElement>;
  onReadFull: () => void;
}

/**
 * Quick View — shows AI summary + a short normalized body preview.
 * All action buttons live in EmailDetailModal's footer.
 */
export function EmailQuickView({ email, actionItemsRef, onReadFull }: Props) {
  const rawText = email.body || email.summary || '';
  const bodyText = normalizeBodyText(rawText);
  const preview = bodyText.length > 320 ? bodyText.slice(0, 320) + '…' : bodyText;

  return (
    <div className="space-y-6">
      {/* AI Analysis */}
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

      {/* Body Preview */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Preview</h3>
        <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
          <p className="text-sm leading-relaxed text-slate-300 whitespace-pre-wrap break-words">
            {preview || 'No preview available.'}
          </p>
          {bodyText.length > 320 && (
            <button
              onClick={onReadFull}
              className="mt-3 text-xs font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Read full email →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
