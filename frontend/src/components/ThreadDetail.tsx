import { useState } from 'react';
import { motion } from 'framer-motion';
import { SummaryResponse } from '../types/api';
import {
    CheckCircle2,
    AlertCircle,
    Calendar,
    Users,
    Copy,
    Check,
    Sparkles,
    MessageSquare
} from 'lucide-react';

interface ThreadDetailProps {
    summary: SummaryResponse;
    onDraftReply?: () => void;
    draftLoading?: boolean;
}

export function ThreadDetail({ summary, onDraftReply, draftLoading }: ThreadDetailProps) {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        const text = `
Summary: ${summary.summary}

Key Points:
${summary.key_points.map((p, i) => `${i + 1}. ${p}`).join('\n')}

Action Items:
${summary.action_items.map((a, i) => `${i + 1}. ${a}`).join('\n')}
        `.trim();

        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card p-8 space-y-8"
        >
            {/* Header */}
            <div className="flex items-start justify-between gap-4">
                <div className="space-y-2">
                    <h2 className="text-3xl font-bold text-white tracking-tight">
                        Thread Summary
                    </h2>
                    <div className="flex items-center gap-2 text-sm text-slate-400">
                        <Sparkles size={16} className="text-primary-500" />
                        <span>Confidence: {Math.round(summary.confidence_score * 100)}%</span>
                    </div>
                </div>

                <button
                    onClick={handleCopy}
                    className="btn-secondary flex items-center gap-2"
                >
                    {copied ? (
                        <>
                            <Check size={16} />
                            Copied!
                        </>
                    ) : (
                        <>
                            <Copy size={16} />
                            Copy
                        </>
                    )}
                </button>
            </div>

            {/* Overview */}
            <div className="space-y-3">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    <MessageSquare size={20} className="text-primary-500" />
                    Overview
                </h3>
                <p className="text-slate-300 leading-relaxed">
                    {summary.summary}
                </p>
            </div>

            {/* Key Points */}
            {summary.key_points.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <AlertCircle size={20} className="text-blue-500" />
                        Key Points
                    </h3>
                    <ul className="space-y-2">
                        {summary.key_points.map((point, index) => (
                            <motion.li
                                key={index}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.05 }}
                                className="flex items-start gap-3 text-slate-300"
                            >
                                <span className="w-6 h-6 rounded-full bg-blue-500/10 text-blue-500 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                                    {index + 1}
                                </span>
                                <span className="leading-relaxed">{point}</span>
                            </motion.li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Action Items */}
            {summary.action_items.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <CheckCircle2 size={20} className="text-green-500" />
                        Action Items
                    </h3>
                    <ul className="space-y-2">
                        {summary.action_items.map((item, index) => (
                            <motion.li
                                key={index}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.05 }}
                                className="flex items-start gap-3 text-slate-300"
                            >
                                <CheckCircle2 size={18} className="text-green-500 shrink-0 mt-0.5" />
                                <span className="leading-relaxed">{item}</span>
                            </motion.li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Deadlines */}
            {summary.deadlines.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <Calendar size={20} className="text-orange-500" />
                        Deadlines
                    </h3>
                    <ul className="space-y-2">
                        {summary.deadlines.map((deadline, index) => (
                            <li key={index} className="flex items-center gap-3 text-slate-300">
                                <Calendar size={16} className="text-orange-500" />
                                <span>{deadline}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Participants */}
            {summary.key_participants.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <Users size={20} className="text-purple-500" />
                        Key Participants
                    </h3>
                    <div className="flex flex-wrap gap-2">
                        {summary.key_participants.map((participant, index) => (
                            <span
                                key={index}
                                className="px-3 py-1.5 bg-purple-500/10 border border-purple-500/20 rounded-full text-purple-400 text-sm font-medium"
                            >
                                {participant}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Draft Reply Button */}
            {onDraftReply && (
                <div className="pt-4 border-t border-white/5">
                    <button
                        onClick={onDraftReply}
                        disabled={draftLoading}
                        className="btn-primary w-full flex items-center justify-center gap-2"
                    >
                        {draftLoading ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                Generating Draft...
                            </>
                        ) : (
                            <>
                                <MessageSquare size={18} />
                                Draft Reply
                            </>
                        )}
                    </button>
                </div>
            )}
        </motion.div>
    );
}
