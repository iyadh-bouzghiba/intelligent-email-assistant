import { motion } from 'framer-motion';
import { Thread } from '../types/api';
import { Clock, TrendingUp, Mail } from 'lucide-react';

interface ThreadListProps {
    threads: Thread[];
    onSelectThread: (threadId: string) => void;
    selectedThreadId?: string;
}

export function ThreadList({ threads, onSelectThread, selectedThreadId }: ThreadListProps) {
    if (threads.length === 0) {
        return (
            <div className="glass-card p-12 text-center space-y-4">
                <Mail className="mx-auto text-slate-600" size={48} />
                <h3 className="text-xl font-bold text-white">No Threads Yet</h3>
                <p className="text-slate-400 max-w-md mx-auto">
                    Simulate an email or connect your Gmail to start analyzing conversations.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-white tracking-tight">
                    Email Threads
                </h2>
                <span className="text-sm text-slate-400">
                    {threads.length} thread{threads.length !== 1 ? 's' : ''}
                </span>
            </div>

            <div className="grid gap-4">
                {threads.map((thread, index) => (
                    <motion.div
                        key={thread.thread_id}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.05 }}
                        onClick={() => onSelectThread(thread.thread_id)}
                        className={`
                            glass-card p-6 cursor-pointer transition-all group
                            ${selectedThreadId === thread.thread_id
                                ? 'border-primary-500/50 bg-primary-500/5'
                                : 'hover:border-primary-500/30'
                            }
                        `}
                    >
                        <div className="space-y-3">
                            <div className="flex items-start justify-between gap-4">
                                <h3 className="text-lg font-semibold text-white line-clamp-2 group-hover:text-primary-400 transition-colors">
                                    {thread.overview}
                                </h3>
                                <div className="flex items-center gap-1.5 text-xs text-slate-500 shrink-0">
                                    <TrendingUp size={14} />
                                    <span>{Math.round(thread.confidence_score * 100)}%</span>
                                </div>
                            </div>

                            {thread.last_updated && (
                                <div className="flex items-center gap-2 text-xs text-slate-500">
                                    <Clock size={14} />
                                    <span>
                                        {new Date(thread.last_updated).toLocaleString()}
                                    </span>
                                </div>
                            )}
                        </div>
                    </motion.div>
                ))}
            </div>
        </div>
    );
}
