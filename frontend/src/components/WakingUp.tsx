import { Brain } from 'lucide-react';
import { motion } from 'framer-motion';

interface WakingUpProps {
    message?: string;
}

const DEFAULT_MESSAGE = 'Starting up - usually takes about 20 seconds on first load.';

export function WakingUp({ message = DEFAULT_MESSAGE }: WakingUpProps) {
    return (
        <motion.div
            key="waking-up-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.35, ease: 'easeOut' } }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="fixed inset-0 z-[400] flex items-center justify-center bg-brand-bg/96 backdrop-blur-md"
            aria-live="polite"
            aria-busy="true"
            role="status"
        >
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] h-[45%] w-[45%] rounded-full bg-primary-500/[0.08] blur-[120px]" />
                <div className="absolute bottom-[-10%] right-[-10%] h-[45%] w-[45%] rounded-full bg-primary-400/[0.08] blur-[120px]" />
            </div>

            <motion.div
                initial={{ opacity: 0, y: 16, scale: 0.985 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8, scale: 0.985 }}
                transition={{ duration: 0.3, ease: 'easeOut' }}
                className="relative mx-6 flex w-full max-w-md flex-col items-center rounded-[28px] border border-brand-border bg-white/[0.04] px-8 py-10 text-center shadow-2xl shadow-primary-950/20"
            >
                <motion.div
                    animate={{ scale: [1, 1.04, 1], opacity: [0.95, 1, 0.95] }}
                    transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
                    className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-600 to-primary-500 shadow-xl shadow-primary-600/25"
                >
                    <Brain size={28} className="text-white" />
                </motion.div>

                <p className="mb-2 text-[11px] font-black uppercase tracking-[0.28em] text-primary-300/90">
                    Executive System Wake
                </p>

                <h1 className="mb-3 text-2xl font-black tracking-tight text-white sm:text-[30px]">
                    EXECUTIVE BRAIN
                </h1>

                <p className="max-w-sm text-sm leading-6 text-slate-300 sm:text-[15px]">
                    {message}
                </p>

                <div className="mt-7 flex items-center gap-2" aria-hidden="true">
                    {[0, 1, 2].map((dot) => (
                        <motion.span
                            key={dot}
                            className="h-2.5 w-2.5 rounded-full bg-primary-400"
                            animate={{ y: [0, -5, 0], opacity: [0.35, 1, 0.35] }}
                            transition={{
                                duration: 0.9,
                                repeat: Infinity,
                                ease: 'easeInOut',
                                delay: dot * 0.16,
                            }}
                        />
                    ))}
                </div>

                <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Warming the service
                </p>
            </motion.div>
        </motion.div>
    );
}
