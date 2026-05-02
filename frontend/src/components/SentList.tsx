import { Clock, Mail, Send, Users } from 'lucide-react';
import { SentEmail } from '@types';

interface Props {
  emails: SentEmail[];
  loading: boolean;
  onSelect: (email: SentEmail) => void;
}

const SENT_SKELETON_COUNT = 5;

function formatSentAt(sentAt: string): string {
  try {
    return new Date(sentAt).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return sentAt;
  }
}

function compactText(value?: string | null): string {
  return (value || '').replace(/\s+/g, ' ').trim();
}

function cardLabel(email: SentEmail): string {
  const subject = compactText(email.subject) || 'No subject';
  const recipient = compactText(email.to_address) || 'unknown recipient';
  return `Open sent email: ${subject}. Sent to ${recipient}.`;
}

export function SentList({ emails, loading, onSelect }: Props) {
  if (loading) {
    return (
      <div className="flex flex-col gap-4" aria-label="Loading sent emails">
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
        <div className="w-24 h-24 rounded-full bg-indigo-500/[0.06] flex items-center justify-center text-indigo-300 border border-indigo-400/10 relative shadow-inner">
          <Send size={38} className="text-indigo-300/45" />
        </div>
        <div className="max-w-sm">
          <h3 className="text-xl font-black text-white mb-2">No Sent Emails</h3>
          <p className="text-slate-400 text-sm leading-relaxed font-medium">
            Sent messages from this account will appear here after you send a reply from Executive Brain.
          </p>
          <p className="text-slate-600 text-xs mt-3 leading-relaxed">
            This view only shows messages sent through the app.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {emails.map((email) => {
        const subject = compactText(email.subject) || '(No Subject)';
        const preview = compactText(email.body_preview);
        const toAddress = compactText(email.to_address) || 'Unknown recipient';
        const ccAddresses = compactText(email.cc_addresses);

        return (
          <button
            key={email.id}
            type="button"
            aria-label={cardLabel(email)}
            onClick={() => onSelect(email)}
            className="group text-left w-full rounded-2xl bg-white/[0.025] border border-white/[0.07] hover:bg-white/[0.045] hover:border-indigo-400/20 transition-all duration-200 shadow-xl overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70"
          >
            <div className="p-4 sm:p-5 flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3 min-w-0">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-wider border bg-indigo-500/10 text-indigo-300 border-indigo-400/20 flex-shrink-0">
                    <Send size={10} />
                    Sent
                  </span>
                  <span className="text-[10px] font-black text-slate-600 uppercase tracking-[0.18em] flex-shrink-0">
                    To
                  </span>
                  <span className="text-xs font-semibold text-slate-300 truncate">
                    {toAddress}
                  </span>
                </div>

                <div className="flex items-center gap-1.5 text-[10px] text-slate-600 flex-shrink-0 pt-0.5">
                  <Clock size={11} className="text-indigo-400/55" />
                  <span>{formatSentAt(email.sent_at)}</span>
                </div>
              </div>

              {ccAddresses && (
                <div className="flex items-center gap-2 min-w-0 text-[11px] text-slate-500">
                  <Users size={12} className="text-slate-600 flex-shrink-0" />
                  <span className="font-bold uppercase tracking-wider text-slate-600 flex-shrink-0">cc</span>
                  <span className="truncate">{ccAddresses}</span>
                </div>
              )}

              <div className="min-w-0">
                <h3 className="text-base sm:text-[17px] font-black text-white group-hover:text-indigo-300 transition-colors leading-snug truncate">
                  {subject}
                </h3>

                {preview ? (
                  <p className="mt-2 text-sm text-slate-400 leading-relaxed line-clamp-2 break-words">
                    {preview}
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-slate-600 italic">
                    No preview available.
                  </p>
                )}
              </div>

              <div className="pt-1 flex items-center justify-between gap-3">
                <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">
                  <Mail size={11} className="text-slate-600" />
                  Outbound message
                </span>
                <span className="text-[10px] font-black uppercase tracking-[0.18em] text-indigo-500/80 opacity-0 group-hover:opacity-100 transition-opacity">
                  Open
                </span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
