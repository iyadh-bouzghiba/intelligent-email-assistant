import React from 'react';
import { SummaryResponse } from '@types';

interface ResultsCardProps {
    summary: SummaryResponse;
}

export const ResultsCard: React.FC<ResultsCardProps> = ({ summary }) => {
    return (
        <div className="bg-white rounded-xl shadow-lg p-6 border border-slate-100 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="mb-6">
                <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-2">Summary</h3>
                <p className="text-slate-800 text-lg leading-relaxed">
                    {summary.summary}
                </p>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
                <div>
                    <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Key Points</h3>
                    <ul className="space-y-2">
                        {summary.key_points.map((point, index) => (
                            <li key={index} className="flex items-start">
                                <span className="text-blue-500 mr-2">•</span>
                                <span className="text-slate-700">{point}</span>
                            </li>
                        ))}
                    </ul>
                </div>

                <div>
                    <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Action Items</h3>
                    <ul className="space-y-2">
                        {summary.action_items.map((item, index) => (
                            <li key={index} className="flex items-start">
                                <span className="text-emerald-500 mr-2">✓</span>
                                <span className="text-slate-700">{item}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            </div>

            {(summary.deadlines?.length > 0 || summary.key_participants?.length > 0) && (
                <div className="mt-6 pt-6 border-t border-slate-100 grid md:grid-cols-2 gap-6">
                    {summary.deadlines?.length > 0 && (
                        <div>
                            <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-2">Deadlines</h3>
                            <div className="flex flex-wrap gap-2">
                                {summary.deadlines.map((deadline, index) => (
                                    <span key={index} className="bg-orange-50 text-orange-700 text-xs font-medium px-2.5 py-0.5 rounded-full border border-orange-100">
                                        {deadline}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                    {summary.key_participants?.length > 0 && (
                        <div>
                            <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-2">Key Participants</h3>
                            <div className="flex flex-wrap gap-2">
                                {summary.key_participants.map((person, index) => (
                                    <span key={index} className="bg-indigo-50 text-indigo-700 text-xs font-medium px-2.5 py-0.5 rounded-full border border-indigo-100">
                                        {person}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            <div className="mt-6 flex items-center justify-between text-xs text-slate-400 italic">
                <span>Confidence Score: {(summary.confidence_score * 100).toFixed(0)}%</span>
                {summary.last_updated && <span>Last Updated: {new Date(summary.last_updated).toLocaleString()}</span>}
            </div>
        </div>
    );
};
