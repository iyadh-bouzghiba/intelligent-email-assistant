import { io, Socket } from "socket.io-client";

const IS_DEV = import.meta.env.DEV;
const DEV_SOCKET_ENABLED = import.meta.env.VITE_ENABLE_SOCKET_DEV === "1";
let lastDevErrAt = 0;
let devSocketNoticeShown = false;

interface ThreadAnalyzedData {
    thread_id: string;
    summary: {
        thread_id: string;
        summary: string;
        key_points: string[];
        action_items: string[];
        confidence_score: number;
    };
    timestamp: string;
}

export type EmailsUpdatedData =
    | { count: number; timestamp?: string }
    | { count_new: number; timestamp?: string };

export interface SummaryReadyData {
    count_summarized: number;
}

interface WebSocketEventMap {
    thread_analyzed: ThreadAnalyzedData;
    emails_updated: EmailsUpdatedData;
    summary_ready: SummaryReadyData;
}

type WebSocketEventName = keyof WebSocketEventMap;
type WebSocketListener<K extends WebSocketEventName> = (payload: WebSocketEventMap[K]) => void;

type ListenerRegistry = {
    [K in WebSocketEventName]?: Array<WebSocketListener<K>>;
};

class WebSocketService {
    private socket: Socket | null = null;
    private listeners: ListenerRegistry = {};

    private getSocketUrl(): string {
        // Production: same-origin (frontend served by backend).
        if (import.meta.env.PROD) {
            return window.location.origin;
        }
        // Dev: use VITE_SOCKET_URL if set, else fallback to localhost backend.
        const url = import.meta.env.VITE_SOCKET_URL || "http://localhost:8000";
        return url.replace(/\/$/, "");
    }

    connect() {
        if (IS_DEV && !DEV_SOCKET_ENABLED) {
            if (!devSocketNoticeShown) {
                devSocketNoticeShown = true;
                console.warn("[WebSocket] DEV sockets disabled (set VITE_ENABLE_SOCKET_DEV=1 to enable).");
            }
            return;
        }

        if (this.socket?.connected) {
            console.log("[WebSocket] Already connected");
            return;
        }

        const SOCKET_URL = this.getSocketUrl();

        const isLocalSocket =
            SOCKET_URL.includes("127.0.0.1:5173") ||
            SOCKET_URL.includes("localhost:5173");

        const socketOptions = {
            path: "/socket.io",
            secure: true,
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            timeout: 20000,
            ...(IS_DEV && isLocalSocket
                ? { transports: ["websocket"] }
                : IS_DEV
                    ? { transports: ["polling"], upgrade: false, rememberUpgrade: false }
                    : { transports: ["websocket", "polling"] }),
        };

        this.socket = io(SOCKET_URL, socketOptions);

        this.socket.on("connect", () => {
            console.log("[WebSocket] Connected:", this.socket?.id);
        });

        this.socket.on("disconnect", (reason) => {
            console.warn("[WebSocket] Disconnected:", reason);
        });

        this.socket.on("connect_error", (error) => {
            if (IS_DEV) {
                const now = Date.now();
                if (now - lastDevErrAt < 5000) return;
                lastDevErrAt = now;
            }
            console.warn("[WebSocket] connect_error:", error?.message ?? error);
        });

        this.socket.on("connection_established", (data) => {
            console.log("[WebSocket] Server handshake:", data);
        });

        this.socket.on("thread_analyzed", (data: ThreadAnalyzedData) => {
            console.log("[WebSocket] Thread analyzed:", data);
            this.emit("thread_analyzed", data);
        });

        this.socket.on("emails_updated", (data: EmailsUpdatedData) => {
            console.log("[WebSocket] Emails updated:", data);
            this.emit("emails_updated", data);
        });

        this.socket.on("summary_ready", (data: SummaryReadyData) => {
            console.log("[WebSocket] Summary ready:", data);
            this.emit("summary_ready", data);
        });
    }

    disconnect() {
        if (this.socket) {
            this.socket.removeAllListeners();
            this.socket.disconnect();
            this.socket = null;
        }
    }

    on<K extends WebSocketEventName>(event: K, callback: WebSocketListener<K>) {
        const eventListeners = (this.listeners[event] ??= []) as Array<WebSocketListener<K>>;
        eventListeners.push(callback);
    }

    off<K extends WebSocketEventName>(event: K, callback: WebSocketListener<K>) {
        const eventListeners = this.listeners[event] as Array<WebSocketListener<K>> | undefined;
        if (!eventListeners) return;

        const index = eventListeners.indexOf(callback);
        if (index > -1) {
            eventListeners.splice(index, 1);
        }

        if (eventListeners.length === 0) {
            delete this.listeners[event];
        }
    }

    private emit<K extends WebSocketEventName>(event: K, data: WebSocketEventMap[K]) {
        const eventListeners = this.listeners[event] as Array<WebSocketListener<K>> | undefined;
        if (!eventListeners) return;

        eventListeners.forEach((callback) => callback(data));
    }

    isConnected(): boolean {
        return this.socket?.connected ?? false;
    }
}

// Export singleton instance
export const websocketService = new WebSocketService();
