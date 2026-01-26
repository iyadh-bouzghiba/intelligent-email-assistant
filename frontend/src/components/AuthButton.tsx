import { LogIn, LogOut } from 'lucide-react';
import { apiService } from '../services/api';

interface AuthButtonProps {
    isAuthenticated?: boolean;
    userEmail?: string;
}

export function AuthButton({ isAuthenticated, userEmail }: AuthButtonProps) {
    const handleLogin = () => {
        window.location.href = apiService.getGoogleAuthUrl();
    };

    if (isAuthenticated) {
        return (
            <div className="flex items-center gap-3">
                <span className="text-sm text-slate-400 hidden sm:block">
                    {userEmail || 'Connected'}
                </span>
                <button className="btn-secondary flex items-center gap-2 text-sm">
                    <LogOut size={16} />
                    <span className="hidden sm:inline">Disconnect</span>
                </button>
            </div>
        );
    }

    return (
        <button
            onClick={handleLogin}
            className="btn-primary flex items-center gap-2 text-sm group"
        >
            <LogIn size={16} className="group-hover:scale-110 transition-transform" />
            <span>Add Gmail Account</span>
        </button>
    );
}
