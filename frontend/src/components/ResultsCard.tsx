import type { SummaryResponse } from '../types/api';
import { CheckCircle2, ListFilter, MessageSquare, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import { motion } from 'framer-motion';

interface ResultsCardProps {
    summary: SummaryResponse;
}

export function ResultsCard({ summary }: ResultsCardProps) {
    const [copied, setCopied] = useState(false);

    const copyToClipboard = () => {
        const text = `
Overview: ${summary.overview}
Key Points: ${summary.key_points.join(', ')}
Action Items: ${summary.action_items.join(', ')}
    `.trim();
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card overflow-hidden"
        >
            <div className="p-6 md:p-8 space-y-8">
                {/* Header */}
                <div className="flex items-start justify-between">
                    <div className="space-y-1">
                        <h2 className="text-2xl font-bold text-white tracking-tight">Analysis Results</h2>
                        <p className="text-slate-400 text-sm">AI-generated summary and insights</p>
                    </div>
                    <button
                        onClick={copyToClipboard}
                        className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 transition-all active:scale-95 text-slate-400 hover:text-white"
                        title="Copy to clipboard"
                    >
                        {copied ? <Check size={20} className="text-emerald-400" /> : <Copy size={20} />}
                    </button>
                </div>

                {/* Overview */}
                <section className="space-y-3">
                    <div className="flex items-center gap-2 text-primary-400">
                        <MessageSquare size={18} />
                        <h3 className="font-semibold uppercase tracking-wider text-xs">Overview</h3>
                    </div>
                    <p className="text-slate-200 leading-relaxed text-lg">
                        {summary.overview}
                    </p>
                </section>

                <div className="grid md:grid-cols-2 gap-8 pt-4">
                    {/* Key Points */}
                    <section className="space-y-4">
                        <div className="flex items-center gap-2 text-primary-400">
                            <ListFilter size={18} />
                            <h3 className="font-semibold uppercase tracking-wider text-xs">Key Points</h3>
                        </div>
                        <ul className="space-y-3">
                            {summary.key_points.map((point, i) => (
                                <li key={i} className="flex items-start gap-3 text-slate-300 text-sm leading-snug">
                                    <div className="w-1.5 h-1.5 rounded-full bg-primary-500 mt-1.5 shrink-0" />
                                    {point}
                                </li>
                            ))}
                        </ul>
                    </section>

                    {/* Action Items */}
                    <section className="space-y-4">
                        <div className="flex items-center gap-2 text-primary-400">
                            <CheckCircle2 size={18} />
                            <h3 className="font-semibold uppercase tracking-wider text-xs">Action Items</h3>
                        </div>
                        <ul className="space-y-3">
                            {summary.action_items.map((item, i) => (
                                <li key={i} className="flex items-start gap-3 bg-white/5 border border-white/5 rounded-xl p-3 text-slate-300 text-sm">
                                    <span className="text-primary-500 font-bold shrink-0">{i + 1}.</span>
                                    {item}
                                </li>
                            ))}
                        </ul>
                    </section>
                </div>
            </div>
        </motion.div>
    );
}
