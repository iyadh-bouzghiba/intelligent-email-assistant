import { StatusBadge } from './StatusBadge';
import { Mail } from 'lucide-react';

export function Navbar() {
    return (
        <nav className="fixed top-0 left-0 right-0 z-50 px-4 py-4">
            <div className="max-w-6xl mx-auto flex items-center justify-between glass px-6 py-3 rounded-2xl shadow-xl">
                <div className="flex items-center gap-2.5">
                    <div className="w-10 h-10 bg-primary-600 rounded-xl flex items-center justify-center shadow-lg shadow-primary-500/20">
                        <Mail className="text-white" size={24} />
                    </div>
                    <div>
                        <h1 className="text-lg font-bold leading-none tracking-tight">Email Assistant</h1>
                        <p className="text-[10px] text-slate-400 font-medium uppercase tracking-widest mt-0.5">Intelligent AI</p>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <StatusBadge />
                </div>
            </div>
        </nav>
    );
}
