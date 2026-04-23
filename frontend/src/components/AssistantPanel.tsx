import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Bot, X, Send, RefreshCw, Sparkles, AlertCircle, CheckCircle } from 'lucide-react';
import { Briefing } from '@types';

const BASE_URL: string = import.meta.env.PROD
  ? window.location.origin
  : (import.meta.env.VITE_API_BASE ?? 'http://localhost:8000').replace(/\/$/, '');

interface Props {
  email: Briefing;
  /** Called with the generated draft text; the caller populates ReplyComposeModal. */
  onUseDraft: (draft: string) => void;
  onClose: () => void;
}

type PanelState =
  | 'checking'
  | 'consent_required'
  | 'ready'
  | 'generating'
  | 'draft_ready'
  | 'error';

/**
 * AI Assistant panel — BL-08/BL-09.
 *
 * Send safety: this component never sends email. Clicking "Use this draft"
 * populates the caller's compose state; the user reviews and sends via
 * ReplyComposeModal, which remains the sole send surface.
 *
 * Approval gate: on first open, calls GET /api/agent/status. If not approved,
 * shows consent UI. POST /api/agent/consent records explicit user approval
 * before any draft action is attempted.
 *
 * Rate limit: the backend enforces 10 agent actions per account per hour.
 * The remaining quota is reflected in the footer.
 */
export function AssistantPanel({ email, onUseDraft, onClose }: Props) {
  const [state, setState] = useState<PanelState>('checking');
  const [instruction, setInstruction] = useState('');
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rateLimitRemaining, setRateLimitRemaining] = useState(10);
  const [consenting, setConsenting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    checkStatus();
  }, [email.account]);

  useEffect(() => {
    if (state === 'ready' && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [state]);

  const checkStatus = async () => {
    setState('checking');
    setError(null);
    try {
      const res = await axios.get(`${BASE_URL}/api/agent/status`, {
        params: { account_id: email.account },
        withCredentials: true,
      });
      setRateLimitRemaining(res.data.rate_limit_remaining ?? 10);
      setState(res.data.approved ? 'ready' : 'consent_required');
    } catch {
      setState('error');
      setError('Could not check assistant status.');
    }
  };

  const handleConsent = async () => {
    setConsenting(true);
    setError(null);
    try {
      await axios.post(
        `${BASE_URL}/api/agent/consent`,
        { account_id: email.account },
        { withCredentials: true }
      );
      setState('ready');
    } catch {
      setError('Failed to enable AI assistant.');
    } finally {
      setConsenting(false);
    }
  };

  const handleGenerate = async () => {
    if (!instruction.trim() || !email.thread_id) return;
    setState('generating');
    setError(null);
    try {
      const res = await axios.post(
        `${BASE_URL}/api/threads/${email.thread_id}/draft`,
        {
          account_id: email.account,
          user_instruction: instruction,
          conversation_id: conversationId,
        },
        { withCredentials: true }
      );
      setDraft(res.data.draft ?? '');
      setConversationId(res.data.conversation_id ?? null);
      setRateLimitRemaining((prev) => Math.max(0, prev - 1));
      setState('draft_ready');
    } catch (e: any) {
      if (e.response?.status === 429) {
        setError('Rate limit reached (10/hour). Try again next hour.');
      } else if (e.response?.status === 403) {
        setState('consent_required');
        return;
      } else {
        setError(e.response?.data?.detail ?? 'Draft generation failed.');
      }
      setState('ready');
    }
  };

  const sendFeedback = async (outcome: string) => {
    if (!conversationId) return;
    try {
      await axios.post(
        `${BASE_URL}/api/agent/feedback`,
        {
          account_id: email.account,
          conversation_id: conversationId,
          action_type: 'draft_reply',
          subject: (email.subject ?? '').slice(0, 500),
          outcome,
        },
        { withCredentials: true }
      );
    } catch {
      // Feedback is best-effort; ignore failure
    }
  };

  const handleUseDraft = async () => {
    await sendFeedback('accepted');
    onUseDraft(draft);
  };

  const handleRegenerate = () => {
    setState('ready');
    setDraft('');
  };

  const handleClose = async () => {
    if (draft && state === 'draft_ready') {
      await sendFeedback('rejected');
    }
    onClose();
  };

  const canGenerate =
    instruction.trim().length > 0 &&
    !!email.thread_id &&
    rateLimitRemaining > 0;

  return (
    <div className="flex flex-col h-full bg-[#0c1526] border-l border-white/[0.08]">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-white/[0.08]">
        <div className="flex items-center gap-2">
          <Bot size={15} className="text-indigo-400" />
          <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
            AI Assistant
          </span>
        </div>
        <button
          onClick={handleClose}
          aria-label="Close AI assistant"
          className="p-1.5 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-white transition-colors"
        >
          <X size={14} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">

        {/* Checking */}
        {state === 'checking' && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <RefreshCw size={12} className="animate-spin" />
            Checking assistant status…
          </div>
        )}

        {/* Error */}
        {state === 'error' && (
          <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
            <AlertCircle size={13} className="flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Consent required */}
        {state === 'consent_required' && (
          <div className="space-y-3">
            <div className="p-4 rounded-2xl bg-indigo-500/[0.07] border border-indigo-500/20 space-y-3">
              <div className="flex items-center gap-2">
                <Sparkles size={13} className="text-indigo-400" />
                <p className="text-xs font-bold text-indigo-300">Enable AI Assistant</p>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                The AI assistant drafts replies for your review. It will never send email on
                your behalf — you review and send every message through the compose window.
              </p>
              <p className="text-[10px] text-slate-500 leading-relaxed">
                Draft actions are limited to 10 per hour. Your email subjects (not body
                content) may be used to improve future suggestions.
              </p>
            </div>
            {error && <p className="text-xs text-rose-400">{error}</p>}
            <button
              onClick={handleConsent}
              disabled={consenting}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold transition-colors"
            >
              {consenting
                ? <><RefreshCw size={12} className="animate-spin" /> Enabling…</>
                : <><Sparkles size={12} /> Enable AI Assistant</>}
            </button>
          </div>
        )}

        {/* Ready / Generating: instruction input */}
        {(state === 'ready' || state === 'generating') && (
          <div className="space-y-4">
            <div className="space-y-0.5">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Email</p>
              <p className="text-xs text-slate-300 font-medium truncate">{email.subject}</p>
              <p className="text-[10px] text-slate-500 truncate">From {email.sender}</p>
            </div>

            {error && (
              <div className="flex items-start gap-2 px-3 py-2 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                Instruction
              </label>
              <textarea
                ref={textareaRef}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && canGenerate) {
                    e.preventDefault();
                    handleGenerate();
                  }
                }}
                placeholder="e.g. Acknowledge receipt and say I'll respond by Friday…"
                rows={4}
                disabled={state === 'generating'}
                className="w-full p-3 rounded-xl bg-white/[0.04] border border-white/10 text-slate-200 placeholder-slate-600 text-xs leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 disabled:opacity-50 transition-all"
              />
            </div>

            <p className="text-[10px] text-slate-600">
              {rateLimitRemaining}/10 actions remaining this hour
            </p>
          </div>
        )}

        {/* Draft ready */}
        {state === 'draft_ready' && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <CheckCircle size={13} className="text-emerald-400" />
              <p className="text-xs font-bold text-emerald-400">
                Draft ready — review before sending
              </p>
            </div>
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08]">
              <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap break-words">
                {draft}
              </p>
            </div>
            <p className="text-[10px] text-slate-500 leading-relaxed">
              "Use this draft" opens the compose window. You review and send — nothing is
              sent automatically.
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex-shrink-0 border-t border-white/[0.08] px-4 py-3">
        {(state === 'ready' || state === 'generating') && (
          <button
            onClick={handleGenerate}
            disabled={!canGenerate || state === 'generating'}
            className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold transition-colors"
          >
            {state === 'generating'
              ? <><RefreshCw size={12} className="animate-spin" /> Generating…</>
              : <><Bot size={12} /> Generate Draft</>}
          </button>
        )}

        {state === 'draft_ready' && (
          <div className="flex flex-col gap-2">
            <button
              onClick={handleUseDraft}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition-colors"
            >
              <Send size={12} />
              Use this draft
            </button>
            <button
              onClick={handleRegenerate}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.08] border border-white/10 text-slate-400 hover:text-white text-xs font-semibold transition-colors"
            >
              <RefreshCw size={12} />
              Regenerate
            </button>
          </div>
        )}

        {state === 'error' && (
          <button
            onClick={checkStatus}
            className="w-full py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.08] text-slate-400 hover:text-white text-xs font-semibold transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
