import axios, { isAxiosError } from "axios";
import {
    SummaryResponse,
    HealthStatus,
    DraftReplyRequest,
    DraftReplyResponse,
    InboxThreadRow,
    ThreadListResponse,
    SimulateEmailRequest,
    BriefingResponse,
    AccountsResponse,
    SendEmailResponse,
    SentEmail,
    SupportedLanguage,
    SupportedTone,
    EmailTemplate,
    CreateTemplateRequest,
    DeleteTemplateResponse,
    AILanguage,
    TemplateLanguage,
} from "@types";

export type { AILanguage } from "@types";

export interface PreferencesResponse {
    account_id: string;
    ai_language: AILanguage;
}

const AUTH_REQUIRED_EVENT = "iea:auth-required";

// Production: same-origin (frontend served by backend, no env var needed).
// Dev: use VITE_API_BASE if set, else localhost fallback.
const BASE_URL: string = import.meta.env.PROD
    ? window.location.origin
    : (import.meta.env.VITE_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");

// Dedicated API root
const API_ROOT = `${BASE_URL}/api`;

const api = axios.create({
    baseURL: BASE_URL,
    headers: {
        "Content-Type": "application/json",
    },
    timeout: 20000,
    withCredentials: true,
});

api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error?.response?.status === 401) {
            window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
        }
        return Promise.reject(error);
    }
);

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

    /**
     * Backend contract for POST /api/threads/{thread_id}/draft
     * Requires account_id + user_instruction; optional conversation_id + tone.
     */
    draftThreadReply: async (
        thread_id: string,
        payload: DraftReplyRequest
    ): Promise<DraftReplyResponse> => {
        const response = await api.post(
            `${API_ROOT}/threads/${encodeURIComponent(thread_id)}/draft`,
            payload
        );
        return response.data;
    },

    sendThreadReply: async (
        thread_id: string,
        body: string,
        subject?: string,
        cc?: string
    ): Promise<SendEmailResponse> => {
        try {
            const response = await api.post(
                `${API_ROOT}/threads/${encodeURIComponent(thread_id)}/send`,
                {
                    body,
                    ...(subject !== undefined ? { subject } : {}),
                    ...(cc ? { cc } : {}),
                }
            );
            return response.data;
        } catch (error: unknown) {
            console.error('[API] sendThreadReply failed:', error);

            const apiError =
                isAxiosError(error) && typeof error.response?.data?.error === 'string'
                    ? error.response.data.error
                    : undefined;

            const message =
                error instanceof Error ? error.message : 'Network error';

            return {
                success: false,
                error: apiError || message
            };
        }
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

    getPreferences: async (account_id: string): Promise<PreferencesResponse> => {
        const response = await api.get(`${API_ROOT}/preferences`, {
            params: { account_id },
        });
        return response.data;
    },

    updatePreferences: async (
        account_id: string,
        ai_language: AILanguage
    ): Promise<PreferencesResponse> => {
        const response = await api.post(`${API_ROOT}/preferences`, {
            account_id,
            ai_language,
        });
        return response.data;
    },

    // REST Emails — primary source for polling
    listEmails: async (account_id?: string): Promise<InboxThreadRow[]> => {
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

    listEmailsWithSummaries: async (
        account_id?: string,
        preferred_language = 'en'
    ): Promise<InboxThreadRow[]> => {
        const params = account_id
            ? { account_id, preferred_language }
            : { preferred_language };

        try {
            const response = await api.get(`${API_ROOT}/emails-with-summaries`, { params });
            console.log(`📡 API: Fetched ${response.data?.length || 0} emails with summaries`);
            return response.data;
        } catch (error) {
            console.warn("📡 API: emails-with-summaries unreachable, falling back to listEmails", error);
            // Final graceful fallback — old endpoint is language-blind and may omit summary metadata
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
                timeout: 30000,
            });
            return response.data;
        } catch (error) {
            console.warn("📡 API: Sync failed, degrading gracefully.");
            return { status: "error" };
        }
    },

    // Thread read/unread writeback — requires gmail.modify scope.
    // account_id is passed explicitly to skip the server-side DB lookup.
    setThreadReadState: async (
        thread_id: string,
        is_read: boolean,
        account_id: string
    ): Promise<{ success: boolean; gmail_updated?: boolean; db_updated?: boolean; db_error?: string; error?: string }> => {
        try {
            const response = await api.post(
                `${API_ROOT}/threads/${encodeURIComponent(thread_id)}/read-state`,
                { is_read, account_id },
                { timeout: 35000 }
            );
            return response.data;
        } catch (error: unknown) {
            console.warn('[API] setThreadReadState failed:', error);

            const apiError =
                isAxiosError(error) && typeof error.response?.data?.error === 'string'
                    ? error.response.data.error
                    : undefined;

            const message =
                error instanceof Error ? error.message : 'Network error';

            return { success: false, error: apiError || message };
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

    // Supported languages — public /api/preferences/languages
    getSupportedLanguages: async (): Promise<SupportedLanguage[]> => {
        try {
            const response = await api.get(`${API_ROOT}/preferences/languages`);
            return response.data ?? [];
        } catch (error) {
            console.warn('📡 API: getSupportedLanguages failed, returning empty list', error);
            return [];
        }
    },

    // Supported draft tones — authenticated /api/tones
    getSupportedTones: async (): Promise<SupportedTone[]> => {
        try {
            const response = await api.get(`${API_ROOT}/tones`);
            return response.data ?? [];
        } catch (error) {
            console.warn('📡 API: getSupportedTones failed, returning empty list', error);
            return [];
        }
    },

    // Reusable templates — authenticated /api/templates
    listTemplates: async (
        account_id: string,
        language: TemplateLanguage
    ): Promise<EmailTemplate[]> => {
        try {
            const response = await api.get(`${API_ROOT}/templates`, {
                params: { account_id, language },
            });
            return response.data ?? [];
        } catch (error) {
            console.warn('📡 API: listTemplates failed, returning empty list', error);
            return [];
        }
    },

    createTemplate: async (
        payload: CreateTemplateRequest
    ): Promise<EmailTemplate> => {
        const response = await api.post(`${API_ROOT}/templates`, payload);
        return response.data;
    },

    deleteTemplate: async (
        template_id: string,
        account_id: string
    ): Promise<DeleteTemplateResponse> => {
        const response = await api.delete(
            `${API_ROOT}/templates/${encodeURIComponent(template_id)}`,
            { params: { account_id } }
        );
        return response.data;
    },

    // Thread-aware inbox — /api/inbox (one row per thread, sorted by latest activity)
    getInboxThreads: async (
        account_id: string,
        limit = 50,
        preferred_language = 'en'
    ): Promise<InboxThreadRow[]> => {
        try {
            const response = await api.get(`${API_ROOT}/inbox`, {
                params: { account_id, limit, preferred_language },
            });
            return response.data ?? [];
        } catch (error) {
            console.warn('📡 API: getInboxThreads failed, falling back to listEmailsWithSummaries', error);
            return apiService.listEmailsWithSummaries(account_id, preferred_language);
        }
    },

    // Sent emails — /api/sent
    getSentEmails: async (account_id: string, limit = 50, offset = 0): Promise<SentEmail[]> => {
        try {
            const response = await api.get(`${API_ROOT}/sent`, {
                params: { account_id, limit, offset },
            });
            return response.data ?? [];
        } catch (error) {
            console.warn('📡 API: getSentEmails failed, returning empty list', error);
            return [];
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
