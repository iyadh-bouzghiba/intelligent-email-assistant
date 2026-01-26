import { io, Socket } from 'socket.io-client';

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

    connect(url: string = 'http://localhost:8000') {
        if (this.socket?.connected) {
            console.log('[WebSocket] Already connected');
            return;
        }

        this.socket = io(url, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionAttempts: 5
        });

        this.socket.on('connect', () => {
            console.log('[WebSocket] Connected to server');
        });

        this.socket.on('disconnect', () => {
            console.log('[WebSocket] Disconnected from server');
        });

        this.socket.on('connection_established', (data) => {
            console.log('[WebSocket] Connection established:', data);
        });

        this.socket.on('thread_analyzed', (data: ThreadAnalyzedData) => {
            console.log('[WebSocket] Thread analyzed:', data);
            this.emit('thread_analyzed', data);
        });

        this.socket.on('connect_error', (error) => {
            console.error('[WebSocket] Connection error:', error);
        });
    }

    disconnect() {
        if (this.socket) {
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
        if (eventListeners) {
            const index = eventListeners.indexOf(callback);
            if (index > -1) {
                eventListeners.splice(index, 1);
            }
        }
    }

    private emit(event: string, data: any) {
        const eventListeners = this.listeners.get(event);
        if (eventListeners) {
            eventListeners.forEach(callback => callback(data));
        }
    }

    isConnected(): boolean {
        return this.socket?.connected ?? false;
    }
}

// Export singleton instance
export const websocketService = new WebSocketService();
