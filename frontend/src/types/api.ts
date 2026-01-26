export interface SummaryResponse {
    thread_id: string;
    summary: string; // Backend uses 'summary' not 'overview'
    key_points: string[];
    action_items: string[];
    deadlines: string[];
    key_participants: string[];
    confidence_score: number;
    classification?: any; // Optional classification result
}

export interface Thread {
    thread_id: string;
    overview: string;
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
    category: 'Security' | 'Financial' | 'General';
    should_alert: boolean;
    summary: string;
    action: string;
}

export interface BriefingResponse {
    account: string;
    briefings: Briefing[];
    error?: string;
    login_url?: string;
}
