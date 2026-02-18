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

class WebSocketService {
    private socket: Socket | null = null;
    private listeners: Map<string, Function[]> = new Map();

    private getSocketUrl(): string {
        const url = import.meta.env.VITE_SOCKET_URL;

        if (!url) {
            throw new Error("❌ VITE_SOCKET_URL is missing. Deployment blocked.");
        }

        // Drift guard: validate canonical backend or localhost only
        const isCanonical = url.includes("intelligent-email-assistant-3e1a.onrender.com");
        const isLocalDev = url.startsWith("http://localhost");

        if (!isCanonical && !isLocalDev && import.meta.env.PROD) {
            throw new Error("❌ Invalid VITE_SOCKET_URL. Update Render env var to canonical backend (3e1a).");
        }

        // Normalize trailing slash to prevent //socket.io bug
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

        this.socket.on("emails_updated", (data: { count: number; timestamp: string }) => {
            console.log("[WebSocket] Emails updated:", data);
            this.emit("emails_updated", data);
        });
    }

    disconnect() {
        if (this.socket) {
            this.socket.removeAllListeners();
            this.socket.disconnect();
            this.socket = null;
        }
    }

    on(event: string, callback: Function) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event)!.push(callback);
    }

    off(event: string, callback: Function) {
        const eventListeners = this.listeners.get(event);
        if (!eventListeners) return;

        const index = eventListeners.indexOf(callback);
        if (index > -1) {
            eventListeners.splice(index, 1);
        }
    }

    private emit(event: string, data: any) {
        const eventListeners = this.listeners.get(event);
        if (!eventListeners) return;

        eventListeners.forEach((callback) => callback(data));
    }

    isConnected(): boolean {
        return this.socket?.connected ?? false;
    }
}

// Export singleton instance
export const websocketService = new WebSocketService();