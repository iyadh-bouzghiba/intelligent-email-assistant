import React, { useState, useEffect } from 'react';
import { EmailAnalyzer } from '@components';
import { apiService } from '@services';
import { Sparkles, Brain, Shield, ChevronRight } from 'lucide-react';

export function AnalyzePage() {
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
                        <Shield size={14} />
                        <span>Security Lockdown</span>
                    </div>
                    <h1 className="text-5xl lg:text-6xl font-black text-white tracking-tighter mb-6 leading-tight">
                        Connect Your <span className="text-indigo-500 text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-500 text-6xl">Gmail</span> Intelligence.
                    </h1>
                    <p className="text-slate-400 text-xl max-w-2xl mx-auto font-medium leading-relaxed mb-10">
                        Once connected, our proprietary AI layer will begin deep analysis of your email threads to distill high-value intelligence feeds.
                    </p>

                    <button
                        onClick={handleLogin}
                        className="group flex items-center gap-3 px-8 py-4 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white text-lg font-bold transition-all shadow-2xl shadow-indigo-600/30 active:scale-95 mx-auto"
                    >
                        <Brain size={24} />
                        Login with Google
                        <ChevronRight size={20} className="group-hover:translate-x-1 transition-transform" />
                    </button>

                    <div className="mt-16 p-8 rounded-[2.5rem] bg-white/[0.02] border border-white/5 backdrop-blur-sm">
                        <div className="grid md:grid-cols-3 gap-8">
                            <div className="text-left">
                                <h3 className="text-white font-bold mb-2 flex items-center gap-2">
                                    <Sparkles size={16} className="text-indigo-400" />
                                    AI Distillation
                                </h3>
                                <p className="text-slate-500 text-sm leading-relaxed">Compressed intelligence from complex threads.</p>
                            </div>
                            <div className="text-left">
                                <h3 className="text-white font-bold mb-2 flex items-center gap-2">
                                    <Shield size={16} className="text-indigo-400" />
                                    Security First
                                </h3>
                                <p className="text-slate-500 text-sm leading-relaxed">Enterprise-grade encryption and privacy monitoring.</p>
                            </div>
                            <div className="text-left">
                                <h3 className="text-white font-bold mb-2 flex items-center gap-2">
                                    <Brain size={16} className="text-indigo-400" />
                                    Deep Analysis
                                </h3>
                                <p className="text-slate-500 text-sm leading-relaxed">Pattern recognition across your entire comms history.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-2xl mx-auto p-6">
            <h2 className="text-2xl font-bold mb-6 text-white">Analyze Email</h2>
            <EmailAnalyzer />
        </div>
    );
}
