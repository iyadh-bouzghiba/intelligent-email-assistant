import { EmailAnalyzer } from '../components/EmailAnalyzer';

export function AnalyzePage() {
    return (
        <div className="max-w-2xl mx-auto p-6">
            <h2 className="text-2xl font-bold mb-6">Analyze Email</h2>
            <EmailAnalyzer />
        </div>
    );
}
