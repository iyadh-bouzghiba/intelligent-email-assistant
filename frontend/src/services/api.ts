import axios from 'axios';
import {
    AnalyzeRequest,
    SummaryResponse,
    HealthStatus,
    DraftReplyRequest,
    DraftReplyResponse,
    ThreadListResponse,
    SimulateEmailRequest,
    BriefingResponse
} from '../types/api';

// Use environment variable for API URL (handling Vite's import.meta.env)
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8888';

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

export const apiService = {
    // Health check
    checkHealth: async (): Promise<HealthStatus> => {
        const response = await api.get('/api/health');
        return response.data;
    },

    // Executive Briefing
    getBriefing: async (email?: string): Promise<BriefingResponse> => {
        const response = await api.get('/api/briefing', {
            params: email ? { email } : {}
        });
        return response.data;
    },

    // Multi-Account Discovery
    listAccounts: async (): Promise<{ accounts: string[] }> => {
        const response = await api.get('/api/accounts');
        return response.data;
    },

    // Thread Management
    listThreads: async (): Promise<ThreadListResponse> => {
        const response = await api.get('/threads');
        return response.data;
    },

    getThreadSummary: async (threadId: string): Promise<SummaryResponse> => {
        const response = await api.get(`/threads/${threadId}`);
        return response.data;
    },

    analyzeThread: async (threadId: string): Promise<SummaryResponse> => {
        const response = await api.post(`/threads/${threadId}/analyze`);
        return response.data;
    },

    draftThreadReply: async (threadId: string): Promise<DraftReplyResponse> => {
        const response = await api.post(`/threads/${threadId}/draft`);
        return response.data;
    },

    // Demo/Simulation Helper
    simulateEmail: async (emailData: SimulateEmailRequest): Promise<{ thread_id: string }> => {
        const response = await api.post('/simulate-email', emailData);
        return response.data;
    },

    // OAuth
    getGoogleAuthUrl: (): string => {
        return `${API_URL}/auth/google/login`;
    },

    // Legacy methods (kept for backward compatibility, but deprecated)
    /** @deprecated Use thread-centric methods instead */
    analyzeEmail: async (_data: AnalyzeRequest): Promise<SummaryResponse> => {
        throw new Error('analyzeEmail is deprecated. Use thread-centric workflow instead.');
    },

    /** @deprecated Use draftThreadReply instead */
    draftReply: async (_data: DraftReplyRequest): Promise<DraftReplyResponse> => {
        throw new Error('draftReply is deprecated. Use draftThreadReply instead.');
    }
};

