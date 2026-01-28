import React, { useState, useEffect } from 'react';
import { DraftReply } from '@components';
import { apiService } from '@services';
import { Sparkles, Brain, Shield, ChevronRight } from 'lucide-react';

export function DraftPage() {
    const [hasThreads, setHasThreads] = useState<boolean | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const checkThreads = async () => {
            try {
                const response = await apiService.listThreads();
                setHasThreads(response.threads && response.threads.length > 0);
            } catch (error) {
                console.error("Failed to check threads:", error);
                setHasThreads(false);
            } finally {
                setLoading(false);
            }
        };
        checkThreads();
    }, []);

    const handleLogin = () => {
        window.location.href = apiService.getGoogleAuthUrl();
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500"></div>
            </div>
        );
    }

    if (!hasThreads) {
        return (
            <div className="max-w-4xl mx-auto px-6 py-16">
                <div className="text-center">
                    <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-black uppercase tracking-[0.2em] mb-8">
                        <Sparkles size={14} />
                        <span>Intelligence Feed</span>
                    </div>
                    <h1 className="text-5xl lg:text-6xl font-black text-white tracking-tighter mb-6 leading-tight">
                        Power Your <span className="text-indigo-500 text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-500 text-6xl">Replies</span> with AI.
                    </h1>
                    <p className="text-slate-400 text-xl max-w-2xl mx-auto font-medium leading-relaxed mb-10">
                        Connect your Gmail to unlock strategic drafting capabilities. Our AI understands context, tone, and objectives to save you hours every week.
                    </p>

                    <button
                        onClick={handleLogin}
                        className="group flex items-center gap-3 px-8 py-4 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white text-lg font-bold transition-all shadow-2xl shadow-indigo-600/30 active:scale-95 mx-auto"
                    >
                        <Brain size={24} />
                        Login with Google
                        <ChevronRight size={20} className="group-hover:translate-x-1 transition-transform" />
                    </button>

                    <div className="mt-16 grid md:grid-cols-2 gap-8">
                        <div className="p-8 rounded-[2.5rem] bg-white/[0.02] border border-white/5 text-left">
                            <h3 className="text-white font-bold mb-3 flex items-center gap-2">
                                <Shield size={18} className="text-indigo-400" />
                                Context-Aware
                            </h3>
                            <p className="text-slate-500 leading-relaxed text-sm">Our AI analyzes previous interactions to ensure every draft maintains your professional voice and technical accuracy.</p>
                        </div>
                        <div className="p-8 rounded-[2.5rem] bg-white/[0.02] border border-white/5 text-left">
                            <h3 className="text-white font-bold mb-3 flex items-center gap-2">
                                <Sparkles size={18} className="text-indigo-400" />
                                Instant Drafts
                            </h3>
                            <p className="text-slate-500 leading-relaxed text-sm">Generate multiple response options in seconds based on high-level strategic goals you define.</p>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-2xl mx-auto p-6">
            <h2 className="text-2xl font-bold mb-6 text-white">Draft Reply</h2>
            <DraftReply />
        </div>
    );
}
