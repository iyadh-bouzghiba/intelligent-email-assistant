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
        const response = await api.get("/healthz");
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

    // Accounts — API namespace
    listAccounts: async (): Promise<AccountsResponse> => {
        const response = await api.get(`${API_ROOT}/accounts`);
        return response.data;
    },

    disconnectAccount: async (account_id: string): Promise<{ status: string }> => {
        const response = await api.post(`${API_ROOT}/accounts/${encodeURIComponent(account_id)}/disconnect`);
        return response.data;
    },

    disconnectAllAccounts: async (): Promise<{ status: string; deleted_count?: number }> => {
        const response = await api.post(`${API_ROOT}/accounts/disconnect-all`);
        return response.data;
    },

    // REST Emails — primary source for polling
    listEmails: async (account_id?: string): Promise<any[]> => {
        const params = account_id ? { account_id } : {};
        try {
            const response = await api.get(`${API_ROOT}/emails`, { params });
            return response.data;
        } catch {
            try {
                const response = await api.get("/emails", { params });
                return response.data;
            } catch {
                console.warn("📡 API: Emails unreachable, degrading gracefully.");
                return [];
            }
        }
    },

    listEmailsWithSummaries: async (account_id?: string): Promise<any[]> => {
        const params = account_id ? { account_id } : {};
        try {
            const response = await api.get(`${API_ROOT}/emails-with-summaries`, { params });
            console.log(`📡 API: Fetched ${response.data?.length || 0} emails with summaries`);
            return response.data;
        } catch (error) {
            console.warn("📡 API: emails-with-summaries unreachable, falling back to listEmails", error);
            // Fallback to old endpoint if new one fails
            return apiService.listEmails(account_id);
        }
    },

    // OAuth — root endpoint
    getGoogleAuthUrl: (): string => {
        return `${BASE_URL}/auth/google`;
    },

    // User-driven Gmail sync
    syncNow: async (account_id?: string): Promise<{ status: string; count?: number; processed_count?: number }> => {
        try {
            const response = await api.post(`${API_ROOT}/sync-now`, null, {
                params: account_id ? { account_id } : {},
            });
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

    summarizeEmail: async (
        gmail_message_id: string,
        account_id: string
    ): Promise<{ status: string; job_id?: string; message?: string }> => {
        try {
            const response = await api.post(
                `${API_ROOT}/emails/${encodeURIComponent(gmail_message_id)}/summarize`,
                null,
                { params: { account_id } }
            );
            console.log(`📡 API: Email summarization queued for ${gmail_message_id}`);
            return response.data;
        } catch (error) {
            console.warn(`📡 API: Email summarization failed for ${gmail_message_id}`, error);
            return { status: "error", message: "Network error" };
        }
    },
};