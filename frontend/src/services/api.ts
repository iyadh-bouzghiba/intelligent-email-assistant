import axios from "axios";
import {
    SummaryResponse,
    HealthStatus,
    DraftReplyResponse,
    ThreadListResponse,
    SimulateEmailRequest,
    BriefingResponse,
    AccountsResponse,
} from "@types";

// Fail-fast environment contract
const RAW_BASE = import.meta.env.VITE_API_BASE;

if (!RAW_BASE) {
    throw new Error("❌ VITE_API_BASE is missing. Deployment blocked.");
}

// Normalize trailing slash
const BASE_URL = RAW_BASE.replace(/\/$/, "");

// Dedicated API root
const API_ROOT = `${BASE_URL}/api`;

const api = axios.create({
    baseURL: BASE_URL,
    headers: {
        "Content-Type": "application/json",
    },
    timeout: 20000,
});

export const apiService = {
    // Health check — root endpoint
    checkHealth: async (): Promise<HealthStatus> => {
        const response = await api.get("/health");
        return response.data;
    },

    // Executive Briefing — root endpoint
    getBriefing: async (email?: string): Promise<BriefingResponse> => {
        const response = await api.get("/process", {
            params: email ? { email } : {},
        });
        return response.data;
    },

    // Thread Management — API namespace
    listThreads: async (): Promise<ThreadListResponse> => {
        const response = await api.get(`${API_ROOT}/threads`);
        return response.data;
    },

    getThreadSummary: async (
        thread_id: string
    ): Promise<SummaryResponse> => {
        const response = await api.get(
            `${API_ROOT}/threads/${thread_id}`
        );
        return response.data;
    },

    analyzeThread: async (
        thread_id: string
    ): Promise<SummaryResponse> => {
        const response = await api.post(
            `${API_ROOT}/threads/${thread_id}/analyze`
        );
        return response.data;
    },

    draftThreadReply: async (
        thread_id: string
    ): Promise<DraftReplyResponse> => {
        const response = await api.post(
            `${API_ROOT}/threads/${thread_id}/draft`
        );
        return response.data;
    },

    simulateEmail: async (
        emailData: SimulateEmailRequest
    ): Promise<{ thread_id: string }> => {
        const response = await api.post(
            `${API_ROOT}/simulate-email`,
            emailData
        );
        return response.data;
    },

    // Backend maps /accounts at root
    listAccounts: async (): Promise<AccountsResponse> => {
        const response = await api.get("/accounts");
        return response.data;
    },

    // REST Emails — primary source for polling
    listEmails: async (): Promise<any[]> => {
        try {
            const response = await api.get("/emails");
            return response.data;
        } catch (error) {
            console.warn("📡 API: Emails unreachable, degrading gracefully.");
            return [];
        }
    },

    // OAuth — root endpoint
    getGoogleAuthUrl: (): string => {
        return `${BASE_URL}/auth/google`;
    },

    // User-driven Gmail sync
    syncNow: async (): Promise<{ status: string; count?: number }> => {
        try {
            const response = await api.post(`${API_ROOT}/sync-now`);
            return response.data;
        } catch (error) {
            console.warn("📡 API: Sync failed, degrading gracefully.");
            return { status: "error" };
        }
    },

    // On-demand thread summarization
    summarizeThread: async (
        thread_id: string
    ): Promise<{ status: string }> => {
        try {
            const response = await api.post(
                `${API_ROOT}/threads/${thread_id}/summarize`
            );
            return response.data;
        } catch (error) {
            console.warn(
                `📡 API: Summarization failed for ${thread_id}, degrading gracefully.`
            );
            return { status: "error" };
        }
    },
};