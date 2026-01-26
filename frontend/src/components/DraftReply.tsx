import { useState } from 'react';
import { apiService } from '../services/api';

export function DraftReply() {
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

            setDraft(result.draft);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                    Subject
                </label>
                <input
                    value={emailSubject}
                    onChange={(e) => setEmailSubject(e.target.value)}
                    className="w-full p-2 border rounded-md"
                />
            </div>

            <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                    Email Content
                </label>
                <textarea
                    value={emailText}
                    onChange={(e) => setEmailText(e.target.value)}
                    rows={6}
                    className="w-full p-2 border rounded-md"
                />
            </div>

            <button
                onClick={handleDraftReply}
                disabled={loading || !emailText.trim()}
                className="bg-blue-600 text-white px-4 py-2 rounded-md"
            >
                {loading ? 'Generating…' : 'Generate Draft'}
            </button>

            {error && (
                <div className="text-red-600 bg-red-100 p-2 rounded">
                    {error}
                </div>
            )}

            {draft && (
                <textarea
                    value={draft}
                    readOnly
                    rows={8}
                    className="w-full p-3 bg-gray-50 border rounded-md"
                />
            )}
        </div>
    );
}
