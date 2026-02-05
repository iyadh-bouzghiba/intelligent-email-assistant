/**
 * BUILD-TIME ENVIRONMENT VALIDATION
 * Enforces canonical Render URLs before Vite build inlines them.
 * Fails fast on missing/invalid VITE_* vars to prevent drift.
 */

const CANONICAL_BACKEND = "https://intelligent-email-assistant-3e1a.onrender.com";
const FORBIDDEN_PATTERN = "7za8";

const apiBase = process.env.VITE_API_BASE;
const socketUrl = process.env.VITE_SOCKET_URL;

console.log("[verify-env] Validating build-time environment...");

// Check 1: Required vars must be present
if (!apiBase) {
    console.error("❌ VITE_API_BASE is missing. Set in Render dashboard.");
    process.exit(1);
}

if (!socketUrl) {
    console.error("❌ VITE_SOCKET_URL is missing. Set in Render dashboard.");
    process.exit(1);
}

// Check 2: Must not contain forbidden patterns
if (apiBase.includes(FORBIDDEN_PATTERN)) {
    console.error(`❌ VITE_API_BASE contains forbidden pattern "${FORBIDDEN_PATTERN}".`);
    console.error(`   Current value: ${apiBase}`);
    console.error(`   Expected: ${CANONICAL_BACKEND}`);
    process.exit(1);
}

if (socketUrl.includes(FORBIDDEN_PATTERN)) {
    console.error(`❌ VITE_SOCKET_URL contains forbidden pattern "${FORBIDDEN_PATTERN}".`);
    console.error(`   Current value: ${socketUrl}`);
    console.error(`   Expected: ${CANONICAL_BACKEND}`);
    process.exit(1);
}

// Check 3: Must match canonical backend (production builds only)
const isProduction = process.env.NODE_ENV === "production" || process.env.VITE_ENV === "production";

if (isProduction) {
    if (apiBase !== CANONICAL_BACKEND) {
        console.error(`❌ VITE_API_BASE does not match canonical backend.`);
        console.error(`   Current: ${apiBase}`);
        console.error(`   Expected: ${CANONICAL_BACKEND}`);
        process.exit(1);
    }

    if (socketUrl !== CANONICAL_BACKEND) {
        console.error(`❌ VITE_SOCKET_URL does not match canonical backend.`);
        console.error(`   Current: ${socketUrl}`);
        console.error(`   Expected: ${CANONICAL_BACKEND}`);
        process.exit(1);
    }
}

// All checks passed
console.log("✅ VITE_API_BASE:", apiBase);
console.log("✅ VITE_SOCKET_URL:", socketUrl);
console.log("[verify-env] Environment validation passed.");
