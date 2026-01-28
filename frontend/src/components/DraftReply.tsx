import React, { useState } from 'react';
import { apiService } from '@services';
import { DraftReplyResponse } from '@types';
import { Mail, Loader2, AlertCircle, Copy, Check } from 'lucide-react';

export const DraftReply: React.FC = () => {
    const [threadId, setThreadId] = useState('');
    const [result, setResult] = useState<DraftReplyResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    const handleDraft = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!threadId.trim()) return;

        setLoading(true);
        setError(null);
        try {
            const data = await apiService.draftThreadReply(threadId.trim());
            setResult(data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to generate draft. Please check the Thread ID.');
            setResult(null);
        } finally {
            setLoading(false);
        }
    };

    const copyToClipboard = () => {
        if (!result?.draft) return;
        navigator.clipboard.writeText(result.draft);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="space-y-6">
            <form onSubmit={handleDraft} className="relative">
                <div className="flex gap-2">
                    <div className="relative flex-grow">
                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <Mail className="h-5 w-5 text-slate-400" />
                        </div>
                        <input
                            type="text"
                            value={threadId}
                            onChange={(e) => setThreadId(e.target.value)}
                            placeholder="Enter Thread ID to draft reply..."
                            className="block w-full pl-10 pr-3 py-3 border border-slate-200 rounded-xl leading-5 bg-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition-all shadow-sm"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading || !threadId.trim()}
                        className="px-6 py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-md shadow-indigo-200"
                    >
                        {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : 'Generate Draft'}
                    </button>
                </div>
            </form>

            {error && (
                <div className="p-4 bg-rose-50 border border-rose-100 rounded-xl flex items-center gap-3 text-rose-700 animate-in fade-in slide-in-from-top-2">
                    <AlertCircle className="h-5 w-5" />
                    <p className="text-sm font-medium">{error}</p>
                </div>
            )}

            {result && (
                <div className="bg-white rounded-xl shadow-lg border border-slate-100 overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500">
                    <div className="bg-slate-50 px-6 py-4 border-b border-slate-100 flex items-center justify-between">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">Suggested Response</h3>
                        <button
                            onClick={copyToClipboard}
                            className="flex items-center gap-2 text-xs font-medium text-slate-500 hover:text-indigo-600 transition-colors"
                        >
                            {copied ? (
                                <>
                                    <Check className="h-4 w-4 text-emerald-500" />
                                    <span className="text-emerald-500">Copied!</span>
                                </>
                            ) : (
                                <>
                                    <Copy className="h-4 w-4" />
                                    <span>Copy Draft</span>
                                </>
                            )}
                        </button>
                    </div>
                    <div className="p-6">
                        <div className="bg-slate-50/50 rounded-lg p-4 border border-slate-100">
                            <pre className="whitespace-pre-wrap font-sans text-slate-800 leading-relaxed text-sm">
                                {result.draft}
                            </pre>
                        </div>
                    </div>
                </div>
            )}

            {!result && !loading && !error && (
                <div className="text-center py-12 border-2 border-dashed border-slate-100 rounded-2xl bg-slate-50/50">
                    <p className="text-slate-400 font-medium">Your AI-generated draft will appear here.</p>
                </div>
            )}
        </div>
    );
};
