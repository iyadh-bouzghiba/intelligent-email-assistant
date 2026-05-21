export type AILanguage = "en" | "fr" | "ar";
export type TranslationLanguage = "en" | "fr" | "ar";
export type DraftTone = "professional" | "casual" | "concise" | "empathetic";
export type TemplateLanguage = AILanguage | "neutral";

export interface SummaryResponse {
    thread_id: string;
    summary: string;           // CRITICAL: Must be 'summary'
    key_points: string[];
    action_items: string[];
    deadlines: string[];
    key_participants: string[];
    confidence_score: number;
    classification?: unknown | null;
    last_updated?: string;
}

export interface Thread {
    thread_id: string;
    summary: string;
    confidence_score: number;
    last_updated: string | null;
}

export interface ThreadListResponse {
    count: number;
    threads: Thread[];
}

export interface AnalyzeRequest {
    content: string;
    subject?: string;
    sender?: string;
}

export interface HealthStatus {
    status: string;
    timestamp: string;
}

/**
 * Backend contract for POST /api/threads/{thread_id}/draft
 */
export interface DraftReplyRequest {
    account_id: string;
    user_instruction: string;
    conversation_id?: string | null;
    tone?: DraftTone;
}

export interface DraftReplyResponse {
    thread_id: string;
    draft: string;
    conversation_id?: string | null;
    status?: string;
}

export interface InboxThreadRow {
    date?: string | null;
    created_at?: string | null;
    ai_summary_json?: EmailViewModel['ai_summary_json'] | null;
    ai_summary_text?: string | null;
    body?: string | null;
    subject?: string | null;
    sender?: string | null;
    account_id?: string | null;
    ai_summary_model?: string | null;
    ai_summary_language?: string | null;
    ai_summary_is_fallback?: boolean | null;
    ai_preferred_language?: string | null;
    ai_preferred_language_available?: boolean | null;
    gmail_message_id?: string | null;
    thread_id?: string | null;
    thread_count?: number | null;
    is_read?: unknown;
    has_attachments?: boolean | null;
    last_activity_iso?: string | null;
    last_sender?: string | null;
}

export interface SimulateEmailRequest {
    subject: string;
    sender: string;
    body: string;
    recipients?: string[];
    thread_id?: string;
}

export interface BriefingSentMeta {
    toAddress: string;
    ccAddresses?: string | null;
    sentAt: string;
    bodyPreview?: string | null;
}

export interface EmailViewModel {
    account: string;
    subject: string;
    sender: string;
    date: string;
    date_iso?: string | null;
    priority: 'Low' | 'Medium' | 'High';
    category: 'Security' | 'Financial' | 'Work' | 'Personal' | 'Marketing' | 'General';
    should_alert: boolean;
    summary: string;
    action: string;
    body?: string;

    // Sent-detail structured metadata (frontend-only enrichment from SentEmail)
    sentMeta?: BriefingSentMeta;

    // AI summary fields (from backend)
    ai_summary_json?: {
        overview: string;
        action_items: string[];
        urgency: 'low' | 'medium' | 'high';
    };
    ai_summary_text?: string;
    ai_summary_model?: string;
    ai_summary_language?: string | null;
    ai_summary_is_fallback?: boolean;
    ai_preferred_language?: string | null;
    ai_preferred_language_available?: boolean;
    gmail_message_id?: string;
    thread_id?: string; // Gmail thread ID (required for send functionality)
    thread_count?: number;
    is_read?: boolean;  // false = unread (UNREAD label present in Gmail)
    has_attachments?: boolean;
    last_activity_iso?: string | null;
    last_sender?: string | null;
}

export interface SentEmail {
    id: string;
    account_id: string;
    gmail_message_id: string | null;
    thread_id: string | null;
    to_address: string;
    cc_addresses: string | null;
    subject: string | null;
    body_preview: string | null;
    sent_at: string;
    has_attachments?: boolean | null;
}

export interface SupportedLanguage {
    code: AILanguage;
    label: string;
    native: string;
}

export interface SupportedTone {
    code: DraftTone;
    label: string;
}

export interface EmailTemplate {
    id?: string;
    account_id: string;
    name: string;
    tone: DraftTone;
    language: TemplateLanguage;
    body: string;
    created_at?: string;
}

export interface CreateTemplateRequest {
    account_id: string;
    name: string;
    tone?: DraftTone;
    language: TemplateLanguage;
    body: string;
}

export interface DeleteTemplateResponse {
    status: string;
    id: string;
}

export interface EmailViewModelResponse {
    account: string;
    briefings: EmailViewModel[];
    error?: string;
    login_url?: string;
}

export interface AccountInfo {
    account_id: string;
    connected: boolean;
    auth_required?: boolean;   // true = credentials row exists but cannot decrypt (re-auth needed)
    send_scope?: boolean;      // true = gmail.send scope is present
    modify_scope?: boolean;    // true = gmail.modify scope is present (read/unread writeback)
    updated_at?: string | null;
    scopes?: string[];
}

export interface AccountsResponse {
    accounts: AccountInfo[];
}

export interface SendEmailRequest {
    body: string;
    subject?: string;
    cc?: string;
}

export interface SendEmailResponse {
    success: boolean;
    message_id?: string;
    thread_id?: string;
    sent_to?: string;
    sent_cc?: string;
    subject?: string;
    error?: string;
}

/** Frontend-only compose state for a single attachment pending reply send. */
export interface ReplyAttachmentDraft {
    file: File;
    filename: string;
    size: number;
    content_type: string;
    last_modified: number;
}

export interface TranslateRenderResponse {
    gmail_message_id: string;
    target_language: string;
    translation_mode: 'structured_html' | 'text_fallback';
    translation_fidelity: 'preserved' | 'simplified';
    translation_reason_code?: string;
    translated_body_html: string | null;
    translated_body_text: string;
    attachments: unknown[];
    linked_files: unknown[];
    error?: string;
}
