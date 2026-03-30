export interface SummaryResponse {
    thread_id: string;
    summary: string;           // CRITICAL: Must be 'summary'
    key_points: string[];
    action_items: string[];
    deadlines: string[];
    key_participants: string[];
    confidence_score: number;
    classification?: any;
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

export interface DraftReplyRequest {
    content: string;
    subject?: string;
    sender?: string;
}

export interface DraftReplyResponse {
    thread_id: string;
    draft: string;
}

export interface SimulateEmailRequest {
    subject: string;
    sender: string;
    body: string;
    recipients?: string[];
    thread_id?: string;
}

export interface Briefing {
    account: string;
    subject: string;
    sender: string;
    date: string;
    priority: 'Low' | 'Medium' | 'High';
    category: 'Security' | 'Financial' | 'Work' | 'Personal' | 'Marketing' | 'General';
    should_alert: boolean;
    summary: string;
    action: string;

    // AI summary fields (from backend)
    ai_summary_json?: {
        overview: string;
        action_items: string[];
        urgency: 'low' | 'medium' | 'high';
    };
    ai_summary_text?: string;
    ai_summary_model?: string;
    gmail_message_id?: string;
    body?: string;
    thread_id?: string;
}

export interface BriefingResponse {
    account: string;
    briefings: Briefing[];
    error?: string;
    login_url?: string;
}

export interface AccountInfo {
    account_id: string;
    connected: boolean;
    updated_at?: string | null;
    scopes?: string[];
}

export interface AccountsResponse {
    accounts: AccountInfo[];
}

export interface SendEmailRequest {
    body: string;
}

export interface SendEmailResponse {
    success: boolean;
    message_id?: string;
    thread_id?: string;
    error?: string;
}
