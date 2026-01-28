import React, { useState } from 'react';
import { apiService } from '@services';
import { SummaryResponse } from '@types';
import { ResultsCard } from './ResultsCard';
import { Search, Loader2, AlertCircle } from 'lucide-react';

export const EmailAnalyzer: React.FC = () => {
    const [threadId, setThreadId] = useState('');
    const [result, setResult] = useState<SummaryResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleAnalyze = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!threadId.trim()) return;

        setLoading(true);
        setError(null);
        try {
            const data = await apiService.analyzeThread(threadId.trim());
            setResult(data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to analyze thread. Please check the Thread ID.');
            setResult(null);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <form onSubmit={handleAnalyze} className="relative">
                <div className="flex gap-2">
                    <div className="relative flex-grow">
                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <Search className="h-5 w-5 text-slate-400" />
                        </div>
                        <input
                            type="text"
                            value={threadId}
                            onChange={(e) => setThreadId(e.target.value)}
                            placeholder="Enter Thread ID to analyze..."
                            className="block w-full pl-10 pr-3 py-3 border border-slate-200 rounded-xl leading-5 bg-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 sm:text-sm transition-all shadow-sm"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading || !threadId.trim()}
                        className="px-6 py-3 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 shadow-md shadow-blue-200"
                    >
                        {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : 'Analyze'}
                    </button>
                </div>
            </form>

            {error && (
                <div className="p-4 bg-rose-50 border border-rose-100 rounded-xl flex items-center gap-3 text-rose-700 animate-in fade-in slide-in-from-top-2">
                    <AlertCircle className="h-5 w-5" />
                    <p className="text-sm font-medium">{error}</p>
                </div>
            )}

            {result && <ResultsCard summary={result} />}

            {!result && !loading && !error && (
                <div className="text-center py-12 border-2 border-dashed border-slate-100 rounded-2xl bg-slate-50/50">
                    <p className="text-slate-400 font-medium">Results will appear here after analysis.</p>
                </div>
            )}
        </div>
    );
};
