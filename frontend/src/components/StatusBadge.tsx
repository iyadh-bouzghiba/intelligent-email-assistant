import { useEffect, useState } from 'react';
import { apiService } from '../services/api';
import { cn } from '../services/utils';
import { Activity } from 'lucide-react';

export function StatusBadge() {
    const [status, setStatus] = useState<'online' | 'offline' | 'checking'>('checking');

    useEffect(() => {
        const checkStatus = async () => {
            try {
                await apiService.checkHealth();
                setStatus('online');
            } catch (err) {
                setStatus('offline');
            }
        };

        checkStatus();
        const interval = setInterval(checkStatus, 30000); // Check every 30s
        return () => clearInterval(interval);
    }, []);

    return (
        <div className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300",
            status === 'online' ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" :
                status === 'offline' ? "bg-rose-500/10 text-rose-400 border border-rose-500/20" :
                    "bg-white/5 text-slate-400 border border-white/10"
        )}>
            <Activity size={14} className={cn(status === 'online' && "animate-pulse")} />
            <span className="capitalize">{status}</span>
        </div>
    );
}
