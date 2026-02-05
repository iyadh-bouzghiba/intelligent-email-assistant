# SESSION CHECKPOINT — PRE-RESTART LOCKDOWN

**Status:** READY ✅
**Date:** 2026-02-05
**Latest Commit:** `6a613fb` — OAuth token sync + realtime feed updates

---

## CANONICAL URLS (LOCKED — DO NOT CHANGE)

- **Backend:** https://intelligent-email-assistant-3e1a.onrender.com
- **Frontend:** https://intelligent-email-frontend.onrender.com

---

## RENDER ENVIRONMENT VARIABLES REQUIRED

### Frontend Service: `email-assistant-frontend`
```
VITE_API_BASE=https://intelligent-email-assistant-3e1a.onrender.com
VITE_SOCKET_URL=https://intelligent-email-assistant-3e1a.onrender.com
```

### Backend Service: `intelligent-email-assistant`
```
# Database (Supabase)
SUPABASE_URL=<from Supabase dashboard>
SUPABASE_ANON_KEY=<from Supabase dashboard>
SUPABASE_SERVICE_KEY=<from Supabase dashboard>
DATABASE_URL=<PostgreSQL connection string>

# Google OAuth (Gmail)
GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOOGLE_CLIENT_SECRET=<from Google Cloud Console>
GOOGLE_REDIRECT_URI=https://intelligent-email-assistant-3e1a.onrender.com/auth/callback/google
BASE_URL=https://intelligent-email-assistant-3e1a.onrender.com
FRONTEND_URL=https://intelligent-email-frontend.onrender.com

# LLM Provider (Mistral AI)
MISTRAL_API_KEY=<from Mistral AI>
LLM_MODE=api

# Security
FERNET_KEY=<encryption key>
JWT_SECRET_KEY=<secure random key>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# Application Config
ENVIRONMENT=production
WORKER_MODE=true
LOG_LEVEL=INFO
GMAIL_CREDENTIALS_PATH=/etc/secrets/gmail_credentials.json
```

---

## VERIFIED ITEMS ✅

### Git Status
- Working tree: **CLEAN**
- Latest commit: `6a613fb`
- Untracked files: Documentation and tools only (not in production deployment)

### Build Guards (Frontend)
- **verify-env.js**: ✅ PASS
  - Validates VITE_API_BASE and VITE_SOCKET_URL at build time
  - Rejects forbidden patterns ("7za8", "2npf")
  - Enforces canonical backend URL in production builds

- **verify-dist.js**: ✅ PASS
  - Scans compiled bundle for forbidden patterns
  - Current dist/ contains 0 matches for "7za8" or "2npf"

### Build Pipeline
```
node scripts/verify-env.js → tsc → vite build → npm run verify:dist
```

### Deployment Health
- **Frontend (https://intelligent-email-frontend.onrender.com)**: HTTP 200 ✅
- **Backend (/healthz)**: HTTP 200 ✅
- **WebSocket**: Ready (connects at /socket.io, status 101 expected) ✅

### Drift Elimination
- Source code: 0 references to "7za8" or "2npf"
- Compiled bundle: 0 forbidden patterns
- Runtime validation: Enforced via api.ts and websocket.ts (whitelist-based)

---

## COMPLETED PHASES

### Commit `ab2cd6a` — RENDER-FE-FIX-01
- Added verify-env.js (build-time VITE_* validation)
- Updated package.json build pipeline
- Changed render.yaml to use `npm ci` (deterministic builds)
- Removed hardcoded `API_HOST` from App.tsx

### Commit `6a613fb` — OAuth token sync + realtime feed updates
- **Token Flow Fix:**
  - OAuth callback writes to: CredentialStore("default")
  - Worker now reads from: CredentialStore("default") (primary) + file fallback
  - Eliminated token mismatch causing `invalid_grant`

- **Realtime Updates:**
  - Worker emits Socket.IO event `emails_updated` after ingestion
  - Frontend listens and auto-refreshes email list
  - Maintains 30s polling fallback for redundancy

---

## KNOWN REMAINING BLOCKER

**Gmail Invalid Grant Error** (requires user action):
- OAuth tokens need refresh via reauth flow
- User must navigate to: https://intelligent-email-assistant-3e1a.onrender.com/auth/google
- Complete Google consent screen
- Tokens will be stored in CredentialStore("default")
- Worker will automatically load from CredentialStore on next cycle

---

## NEXT PHASE: RT-FLOW-01 (After Reauth)

**Objective:** Verify end-to-end realtime email flow

**Steps:**
1. Complete Gmail reauth via `/auth/google`
2. Verify backend logs show:
   ```
   [OK] [CORE] Loaded Gmail credentials from CredentialStore (default)
   [WORKER] Gmail fetch success: N emails
   [WORKER] Socket.IO event emitted: emails_updated (count=N)
   ```
3. Frontend DevTools verification:
   - Network tab: WebSocket status 101
   - Console: `[WebSocket] Emails updated: {count: N, ...}`
   - Visual: Email list auto-updates without manual refresh

**Expected Outcome:**
- New emails appear in frontend within 60s of Gmail receipt
- No manual refresh required
- Sentinel indicator shows "Active" (green)

---

## ARCHITECTURE NOTES

### Token Flow
```
OAuth Write Path:  /auth/callback/google → CredentialStore("default") → Supabase (encrypted)
Worker Read Path:  CredentialStore("default") [primary] → file [fallback] → run_engine()
```

### Realtime Event Flow
```
Worker ingests emails → Saves to Supabase → Emits "emails_updated" via Socket.IO
Frontend receives event → Calls GET /api/emails → Updates UI
```

### Governance Boundaries (LOCKED)
- **GOV-1**: Summarizer.summarize() is sole AI entry point
- **GOV-2**: AIState is process-local, non-persistent
- **ControlPlane**: Singleton with class-level state (schema_state, store, _policy_cache)
- **Schema verification**: Enforced at startup, blocks writes on mismatch

---

## DEPLOYMENT COMMANDS

### Frontend Redeploy
```bash
# In Render dashboard for email-assistant-frontend:
# 1. Verify env vars: VITE_API_BASE and VITE_SOCKET_URL
# 2. Trigger: "Clear build cache & deploy"
# 3. Verify logs show verify-env PASS and verify-dist PASS
```

### Backend Redeploy
```bash
# Auto-deploys on git push to main
# Worker runs in hybrid mode (same process as FastAPI)
```

---

## SAFE TO RESTART IDE

All production code is committed, pushed, and verified clean. Drift guards are enforced. Services are healthy.

**Resume point:** Complete Gmail reauth, then verify realtime flow.
