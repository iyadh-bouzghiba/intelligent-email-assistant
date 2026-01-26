import { useState } from 'react';
import { apiService } from '../services/api';

export function EmailAnalyzer() {
    const [emailText, setEmailText] = useState('');
    const [emailSubject, setEmailSubject] = useState('');
    const [draft, setDraft] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleDraftReply = async () => {
        setLoading(true);
        setError(null);
        setDraft(null);

        try {
            const result = await apiService.draftReply({
                content: emailText,
                subject: emailSubject,
                sender: 'User',
            });

            // ✅ FIX: normalize optional API response
            setDraft(result.draft ?? null);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-md">
            <h2 className="text-2xl font-bold mb-6 text-gray-800">
                Email Assistant
            </h2>

            <div className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                        Subject
                    </label>
                    <input
                        type="text"
                        value={emailSubject}
                        onChange={(e) => setEmailSubject(e.target.value)}
                        placeholder="Enter email subject"
                        className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                </div>

                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                        Email Content
                    </label>
                    <textarea
                        value={emailText}
                        onChange={(e) => setEmailText(e.target.value)}
                        placeholder="Paste the email content here..."
                        rows={6}
                        className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                </div>

                <button
                    onClick={handleDraftReply}
                    disabled={loading || !emailText.trim()}
                    className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                >
                    {loading ? 'Generating Draft…' : 'Generate Draft Reply'}
                </button>
            </div>

            {error && (
                <div className="mt-4 p-3 bg-red-100 text-red-700 rounded-md border border-red-200">
                    {error}
                </div>
            )}

            {draft && (
                <div className="mt-8">
                    <h3 className="text-lg font-semibold mb-3 text-gray-800">
                        Generated Draft
                    </h3>
                    <textarea
                        value={draft}
                        readOnly
                        rows={8}
                        className="w-full p-3 bg-gray-50 border border-gray-200 rounded-md text-gray-700"
                    />
                </div>
            )}
        </div>
    );
}
