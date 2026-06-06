import { describe, it, expect, vi, beforeEach } from 'vitest';

// Enable socket connections in the test environment before module load.
// The websocket module guards connect() behind IS_DEV && !DEV_SOCKET_ENABLED.
// Hoisted so it runs before module-level constants are captured.
vi.hoisted(() => {
  (import.meta.env as Record<string, unknown>).VITE_ENABLE_SOCKET_DEV = '1';
});

// Mock socket.io-client before importing websocketService
vi.mock('socket.io-client', () => ({
  io: vi.fn(() => ({
    connected: true,
    on: vi.fn(),
    off: vi.fn(),
    emit: vi.fn(),
    disconnect: vi.fn(),
    removeAllListeners: vi.fn(),
  }))
}));

// Import after mock
import { websocketService } from '../websocket';

type MockSocket = {
  connected: boolean;
  on: ReturnType<typeof vi.fn>;
  off: ReturnType<typeof vi.fn>;
  emit: ReturnType<typeof vi.fn>;
  disconnect: ReturnType<typeof vi.fn>;
  removeAllListeners: ReturnType<typeof vi.fn>;
};

type WebSocketServiceWithSocket = {
  socket: MockSocket | null;
};

const getSocket = () =>
  (websocketService as unknown as WebSocketServiceWithSocket).socket;

describe('WebSocket lifecycle contract', () => {

  beforeEach(() => {
    // Ensure clean state before each test
    websocketService.disconnect();
  });

  it('connect() is a no-op when already connected',
  () => {
    // First connect
    websocketService.connect();
    const socket1 = getSocket();

    // Second connect — must not create a new socket
    websocketService.connect();
    const socket2 = getSocket();

    expect(socket1).toBe(socket2);
  });

  it('disconnect() is safe when called multiple times',
  () => {
    websocketService.connect();
    websocketService.disconnect();
    // Second disconnect must not throw
    expect(() => websocketService.disconnect())
      .not.toThrow();
  });

  it('connect() after disconnect creates a fresh socket',
  () => {
    websocketService.connect();
    const socket1 = getSocket();
    websocketService.disconnect();
    websocketService.connect();
    const socket2 = getSocket();
    // After reconnect, a fresh socket exists
    expect(socket2).not.toBeNull();
    expect(socket2).not.toBe(socket1);
  });

});
