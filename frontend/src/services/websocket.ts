import { io, Socket } from "socket.io-client";

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
        if (this.socket?.connected) {
            console.log("[WebSocket] Already connected");
            return;
        }

        const SOCKET_URL = this.getSocketUrl();

        this.socket = io(SOCKET_URL, {
            path: "/socket.io",
            transports: ["websocket"],
            secure: true,
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            timeout: 20000,
        });

        this.socket.on("connect", () => {
            console.log("[WebSocket] Connected:", this.socket?.id);
        });

        this.socket.on("disconnect", (reason) => {
            console.warn("[WebSocket] Disconnected:", reason);
        });

        this.socket.on("connect_error", (error) => {
            console.error("[WebSocket] Connection error:", error.message);
        });

        this.socket.on("connection_established", (data) => {
            console.log("[WebSocket] Server handshake:", data);
        });

        this.socket.on("thread_analyzed", (data: ThreadAnalyzedData) => {
            console.log("[WebSocket] Thread analyzed:", data);
            this.emit("thread_analyzed", data);
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