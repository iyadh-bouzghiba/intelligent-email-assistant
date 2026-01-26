import { Component, ErrorInfo, ReactNode } from "react";
import { AlertCircle } from "lucide-react";

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
    public state: State = {
        hasError: false,
    };

    public static getDerivedStateFromError(_: Error): State {
        return { hasError: true };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error("🔒 [Sentinel ErrorBoundary] Uncaught error:", error, errorInfo);
    }

    public render() {
        if (this.state.hasError) {
            return (
                this.props.fallback || (
                    <div className="p-8 rounded-[2.5rem] bg-rose-500/5 border border-rose-500/10 flex flex-col items-center text-center gap-4">
                        <AlertCircle className="text-rose-500" size={32} />
                        <div>
                            <h4 className="text-white font-bold">Card Integrity Failure</h4>
                            <p className="text-rose-400/60 text-xs">This briefing item failed to render safely.</p>
                        </div>
                    </div>
                )
            );
        }

        return this.props.children;
    }
}
