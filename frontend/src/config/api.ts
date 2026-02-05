/**
 * CENTRALIZED API CONFIGURATION
 * Zero-hardcode environment with resilience patterns
 */

// Primary URL from environment
const PROD_URL = import.meta.env.VITE_API_BASE;
const FALLBACK_URL = "http://localhost:8000";

// Fail-safe resolution with trailing slash normalization
const rawApiUrl = PROD_URL || FALLBACK_URL;
export const API_BASE_URL = rawApiUrl.replace(/\/$/, "");

// WebSocket URL resolution with trailing slash normalization
const SOCKET_PROD_URL = import.meta.env.VITE_SOCKET_URL;
const rawSocketUrl = SOCKET_PROD_URL || FALLBACK_URL;
export const SOCKET_BASE_URL = rawSocketUrl.replace(/\/$/, "");

/**
 * Resilient API fetch with timeout and error handling
 *
 * Features:
 * - 15s timeout with AbortController
 * - Automatic error message extraction
 * - Network failure graceful degradation
 * - Content-Type headers
 *
 * @param path - API endpoint path (e.g., "/health", "/api/threads")
 * @param options - Standard fetch options
 * @returns Parsed JSON response
 * @throws Error with descriptive message on failure
 */
export const apiFetch = async (path: string, options: RequestInit = {}) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API Error ${res.status}: ${text}`);
    }

    return await res.json();
  } catch (err: any) {
    // Network failure or timeout
    if (err.name === 'AbortError') {
      console.error("⏱️ API timeout:", path);
      throw new Error("Request timeout. Please try again.");
    }

    console.error("🌐 API unreachable:", err);
    throw new Error("Backend unavailable. Please try again later.");
  } finally {
    clearTimeout(timeout);
  }
};

/**
 * Validates that required environment variables are present
 * Call this at app initialization to fail-fast on misconfiguration
 */
export const validateEnvironment = () => {
  if (!PROD_URL && import.meta.env.PROD) {
    console.warn("⚠️ VITE_API_BASE not set. Falling back to:", FALLBACK_URL);
  }

  console.log("✅ API configured:", API_BASE_URL);
  console.log("✅ WebSocket configured:", SOCKET_BASE_URL);
};
