import axios from 'axios';
import {
    SummaryResponse,
    HealthStatus,
    DraftReplyResponse,
    ThreadListResponse,
    SimulateEmailRequest,
    BriefingResponse,
    AccountsResponse
} from '@types';

// Syncing with the Render URL
const API_URL = import.meta.env.VITE_API_URL || 'https://intelligent-email-assistant-7za8.onrender.com';

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

export const apiService = {
    // Health check - Fixed path
    checkHealth: async (): Promise<HealthStatus> => {
        const response = await api.get('/health');
        return response.data;
    },

    // Executive Briefing - Fixed path
    getBriefing: async (email?: string): Promise<BriefingResponse> => {
        const response = await api.get('/process', {
            params: email ? { email } : {}
        });
        return response.data;
    },

    // Thread Management
    listThreads: async (): Promise<ThreadListResponse> => {
        const response = await api.get('/threads');
        return response.data;
    },

    getThreadSummary: async (thread_id: string): Promise<SummaryResponse> => {
        const response = await api.get(`/threads/${thread_id}`);
        return response.data;
    },

    analyzeThread: async (thread_id: string): Promise<SummaryResponse> => {
        const response = await api.post(`/threads/${thread_id}/analyze`);
        return response.data;
    },

    draftThreadReply: async (thread_id: string): Promise<DraftReplyResponse> => {
        const response = await api.post(`/threads/${thread_id}/draft`);
        return response.data;
    },

    simulateEmail: async (emailData: SimulateEmailRequest): Promise<{ thread_id: string }> => {
        const response = await api.post('/simulate-email', emailData);
        return response.data;
    },

    listAccounts: async (): Promise<AccountsResponse> => {
        const response = await api.get('/api/accounts');
        return response.data;
    },

    getGoogleAuthUrl: (): string => {
        return `${API_URL}/auth/google/login`;
    }
};