/**
 * BUILD-TIME ENVIRONMENT VALIDATION
 * Enforces canonical Render URLs before Vite build inlines them.
 * Fails fast on missing/invalid VITE_* vars to prevent drift.
 */

import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { existsSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = join(__dirname, '..');

// Guarded dynamic import of dotenv (prevents ESM stack trace if missing)
let config;
try {
  const dotenvModule = await import('dotenv');
  config = dotenvModule.config;
} catch {
  console.error("[verify-env] Missing dependency: dotenv. Run `npm install` in frontend/.");
  process.exit(1);
}


// Load .env files (without overwriting existing process.env)
// Priority: .env.local > .env (Render dashboard vars have highest priority)
const envLocalPath = join(rootDir, '.env.local');
const envPath = join(rootDir, '.env');

if (existsSync(envLocalPath)) {
  config({ path: envLocalPath, override: false });
  console.log('[verify-env] Loaded .env.local');
}

if (existsSync(envPath)) {
  config({ path: envPath, override: false });
  console.log('[verify-env] Loaded .env');
}

const CANONICAL_BACKEND = "https://intelligent-email-assistant-3e1a.onrender.com";
const FORBIDDEN_PATTERN = "7za8";

const apiBase = process.env.VITE_API_BASE;
const socketUrl = process.env.VITE_SOCKET_URL;

console.log("[verify-env] Validating build-time environment...");

// Check 1: Required vars must be present
if (!apiBase) {
  console.error("❌ VITE_API_BASE is missing.");
  console.error("   Create .env.local in frontend/ or set in Render dashboard.");
  process.exit(1);
}

if (!socketUrl) {
  console.error("❌ VITE_SOCKET_URL is missing.");
  console.error("   Create .env.local in frontend/ or set in Render dashboard.");
  process.exit(1);
}

// Check 2: Must not contain forbidden patterns
if (apiBase.includes(FORBIDDEN_PATTERN)) {
  console.error(`❌ VITE_API_BASE contains forbidden pattern "${FORBIDDEN_PATTERN}".`);
  console.error(`   Update to canonical backend: ${CANONICAL_BACKEND}`);
  process.exit(1);
}

if (socketUrl.includes(FORBIDDEN_PATTERN)) {
  console.error(`❌ VITE_SOCKET_URL contains forbidden pattern "${FORBIDDEN_PATTERN}".`);
  console.error(`   Update to canonical backend: ${CANONICAL_BACKEND}`);
  process.exit(1);
}

// Check 3: Must match canonical backend (production builds only)
const isProduction = process.env.NODE_ENV === "production" || process.env.VITE_ENV === "production";

if (isProduction) {
  if (apiBase !== CANONICAL_BACKEND) {
    console.error(`❌ VITE_API_BASE does not match canonical backend.`);
    console.error(`   Expected: ${CANONICAL_BACKEND}`);
    process.exit(1);
  }

  if (socketUrl !== CANONICAL_BACKEND) {
    console.error(`❌ VITE_SOCKET_URL does not match canonical backend.`);
    console.error(`   Expected: ${CANONICAL_BACKEND}`);
    process.exit(1);
  }
}

// All checks passed
console.log("✅ VITE_API_BASE: [set]");
console.log("✅ VITE_SOCKET_URL: [set]");
console.log("[verify-env] Environment validation passed.");
