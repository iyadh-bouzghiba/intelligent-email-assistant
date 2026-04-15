import { Mail, Clock } from 'lucide-react';
import { SentEmail } from '@types';

interface Props {
  emails: SentEmail[];
  loading: boolean;
  onSelect: (email: SentEmail) => void;
}

function formatSentAt(sentAt: string): string {
  try {
    return new Date(sentAt).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return sentAt;
  }
}

export function SentList({ emails, loading, onSelect }: Props) {
  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        {[...Array(3)].map((_, i) => (
          <div
            key={i}
            className="rounded-2xl bg-white/[0.02] border border-white/5 p-5 flex flex-col gap-3 relative overflow-hidden"
          >
            <div className="w-1/3 h-4 rounded-lg bg-white/5 animate-pulse" />
            <div className="w-2/3 h-5 rounded-lg bg-white/5 animate-pulse" />
            <div className="w-full h-10 rounded-xl bg-white/5 animate-pulse" />
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.015] to-transparent -translate-x-full animate-[shimmer_2s_infinite]" />
          </div>
        ))}
      </div>
    );
  }

  if (emails.length === 0) {
    return (
      <div className="w-full py-32 flex flex-col items-center gap-6 text-center">
        <div className="w-24 h-24 rounded-full bg-white/[0.03] flex items-center justify-center text-slate-600 border border-white/5 relative shadow-inner">
          <Mail size={40} className="text-indigo-500/20" />
        </div>
        <div>
          <h3 className="text-xl font-semibold text-white mb-2">No Sent Emails</h3>
          <p className="text-slate-500 max-w-xs font-medium">
            No emails sent from this account yet.
          </p>
          <p className="text-slate-600 text-sm mt-1">
            Emails you send will appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {emails.map((email) => (
        <button
          key={email.id}
          onClick={() => onSelect(email)}
          className="group text-left w-full flex flex-col p-4 sm:p-5 rounded-2xl bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] hover:border-white/10 transition-all duration-200 shadow-xl"
        >
          {/* To / CC row */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">To</span>
            <span className="text-xs font-semibold text-slate-300 truncate">{email.to_address}</span>
            {email.cc_addresses && (
              <>
                <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wider">cc</span>
                <span className="text-xs text-slate-500 truncate">{email.cc_addresses}</span>
              </>
            )}
          </div>

          {/* Subject */}
          <h3 className="text-base font-bold text-white group-hover:text-indigo-400 transition-colors mb-1 truncate">
            {email.subject || '(No Subject)'}
          </h3>

          {/* Body preview */}
          {email.body_preview && (
            <p className="text-xs text-slate-500 leading-relaxed line-clamp-2 mb-3">
              {email.body_preview.length > 80
                ? email.body_preview.slice(0, 80) + '…'
                : email.body_preview}
            </p>
          )}

          {/* Timestamp */}
          <div className="flex items-center gap-1 text-[10px] text-slate-600 mt-auto">
            <Clock size={11} className="text-indigo-400/50" />
            <span>{formatSentAt(email.sent_at)}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
