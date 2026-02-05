# OAUTH CONFIGURATION STANDARD
**Status:** Critical Alignment Required
**Last Updated:** 2026-02-02
**Platform:** Google Cloud Platform

---

## CURRENT ISSUES IDENTIFIED

Based on Google Cloud Console screenshots:

### JavaScript Origins (CURRENT - INCORRECT)
```
❌ http://localhost:8080
❌ http://localhost:8888
❌ https://intelligent-email-assistant-3e1a.onrender.com
❌ https://intelligent-email-assistant-3e1a.onrender.com
```

### Redirect URIs (CURRENT - INCORRECT)
```
❌ http://localhost:8888/auth/google/callback
❌ http://127.0.0.1:8888/auth/google/callback
❌ https://intelligent-email-assistant-3e1a.onrender.com/auth/google/callback
❌ https://intelligent-email-assistant-3e1a.onrender.com/api/auth/callback/google
```

### Problems
1. **Port Mismatch:** Using 8080/8888 but app runs on 8000 (API) and 5173 (Frontend)
2. **Path Inconsistency:** `/auth/google/callback` vs `/auth/callback/google`
3. **Zombie Domain:** `7za8` subdomain is a ghost deployment
4. **Origin Confusion:** JavaScript origins point to backend, should point to frontend

---

## CORRECTED CONFIGURATION

### Step 1: Fix JavaScript Origins

**Location:** Google Cloud Console → OAuth 2.0 Client → Authorized JavaScript origins

**DELETE ALL EXISTING, THEN ADD:**
```
✅ http://localhost:5173
✅ https://intelligent-email-frontend.onrender.com
```

**Why Frontend, Not Backend?**
- OAuth consent happens in the browser
- Browser makes requests from frontend domain
- Backend receives callback but doesn't initiate flow

### Step 2: Fix Redirect URIs

**Location:** Google Cloud Console → OAuth 2.0 Client → Authorized redirect URIs

**DELETE ALL EXISTING, THEN ADD:**
```
✅ http://localhost:8000/auth/callback/google
✅ https://intelligent-email-assistant-3e1a.onrender.com/auth/callback/google
```

**Path Standard:** Always use `/auth/callback/google` (not `/auth/google/callback`)

### Step 3: Fix Authorized Domains

**Location:** Google Cloud Console → OAuth Consent Screen → Branding → Authorized domains

**KEEP:**
```
✅ intelligent-email-assistant-3e1a.onrender.com
✅ intelligent-email-frontend.onrender.com
```

**DELETE:**
```
❌ intelligent-email-assistant-3e1a.onrender.com (zombie deployment)
```

### Step 4: Verify Gmail Scopes

**Location:** Google Cloud Console → Data Access

**REQUIRED SCOPE:**
```
✅ https://www.googleapis.com/auth/gmail.modify
```

**User-facing description:** "Read, compose, and send emails from your Gmail account"

---

## CODE ALIGNMENT

### Backend: Check OAuth Routes

**File:** `backend/src/api/service.py`

**Expected Routes:**
```python
@app.get("/auth/google")
async def google_oauth_init():
    # Initiates OAuth flow
    # Redirects to Google with client_id
    pass

@app.get("/auth/callback/google")  # ← MUST MATCH Google Console
async def google_oauth_callback(code: str):
    # Receives auth code from Google
    # Exchanges for tokens
    # Redirects to frontend with success
    pass
```

**Verification Command:**
```bash
cd intelligent-email-assistant
python -m backend.scripts.verify_routes
```

**Expected Output:**
```
✅ Found routes:
   GET    /auth/google
   GET    /auth/callback/google
```

### Frontend: Check API Configuration

**File:** `frontend/src/config/api.ts`

**Expected:**
```typescript
// Local
const API_BASE_URL = "http://localhost:8000";

// Production (via .env)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
```

**OAuth Flow:**
```
1. User clicks "Sign in with Google" in frontend
2. Frontend redirects to: http://localhost:8000/auth/google
3. Backend redirects to Google with: redirect_uri=http://localhost:8000/auth/callback/google
4. User authorizes on Google
5. Google redirects to: http://localhost:8000/auth/callback/google?code=...
6. Backend processes, redirects to: http://localhost:5173/?auth=success
```

---

## ENVIRONMENT VARIABLES

### Local Development (.env)

```bash
# Backend runs on 8000 (not 8888!)
PORT=8000
BASE_URL=http://localhost:8000

# OAuth Callback
GOOGLE_CLIENT_ID=404491356399-fem39f8euhoffa1jfb341r18rb6ll5pe.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=[from Google Console]
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback/google

# Frontend
FRONTEND_URL=http://localhost:5173
```

### Production (Render - Backend)

```bash
PORT=10000  # Render assigns this
BASE_URL=https://intelligent-email-assistant-3e1a.onrender.com

GOOGLE_CLIENT_ID=404491356399-fem39f8euhoffa1jfb341r18rb6ll5pe.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=[from Google Console]
GOOGLE_REDIRECT_URI=https://intelligent-email-assistant-3e1a.onrender.com/auth/callback/google

FRONTEND_URL=https://intelligent-email-frontend.onrender.com
```

### Production (Render - Frontend)

```bash
VITE_API_BASE_URL=https://intelligent-email-assistant-3e1a.onrender.com
```

---

## CRITICAL FIX REQUIRED: Port 8888 → 8000

**Problem:** Current `.env` has `PORT=8888` but OAuth configured for `8000`

**File:** `intelligent-email-assistant/backend/.env`

**CHANGE FROM:**
```bash
PORT=8888
BASE_URL=http://localhost:8888
REDIRECT_URI=http://localhost:8888/auth/google/callback
```

**CHANGE TO:**
```bash
PORT=8000
BASE_URL=http://localhost:8000
REDIRECT_URI=http://localhost:8000/auth/callback/google
```

**Why This Matters:**
- Google OAuth expects redirect to port in console
- Mismatch = "redirect_uri_mismatch" error
- Worker testing used 8888, but OAuth uses 8000

**Execute Fix:**
```bash
cd intelligent-email-assistant/backend
sed -i 's/PORT=8888/PORT=8000/g' .env
sed -i 's/localhost:8888/localhost:8000/g' .env
sed -i 's|/auth/google/callback|/auth/callback/google|g' .env
```

---

## VERIFICATION CHECKLIST

After making changes, verify each item:

### Google Cloud Console
- [ ] JavaScript origins: Only `localhost:5173` and `frontend.onrender.com`
- [ ] Redirect URIs: Only `/auth/callback/google` paths
- [ ] No port 8080 or 8888 anywhere
- [ ] No `7za8` domain
- [ ] Gmail scope: `gmail.modify` enabled
- [ ] Test users: Your Gmail added (3/100 used)

### Local Environment
- [ ] `.env` has `PORT=8000` (not 8888)
- [ ] `.env` has `REDIRECT_URI=http://localhost:8000/auth/callback/google`
- [ ] Backend starts on port 8000: `uvicorn running on 0.0.0.0:8000`
- [ ] Frontend starts on port 5173: `Local: http://localhost:5173`

### Code Routes
- [ ] Backend has `/auth/google` endpoint
- [ ] Backend has `/auth/callback/google` endpoint (NOT `/auth/google/callback`)
- [ ] Frontend redirects to `${API_BASE_URL}/auth/google`

### Test OAuth Flow
```bash
# 1. Start backend
cd intelligent-email-assistant
python -m backend.src.infrastructure.worker_entry

# 2. Start frontend (separate terminal)
cd intelligent-email-assistant/frontend
npm run dev

# 3. Open browser
http://localhost:5173

# 4. Click "Sign in with Google"
# Expected: Redirects to Google consent screen
# Expected: After consent, returns to http://localhost:5173/?auth=success
```

---

## SUPABASE SCHEMA FOR OAUTH

**Table:** `user_secrets` (stores encrypted OAuth tokens)

```sql
CREATE TABLE user_secrets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,

  provider TEXT NOT NULL CHECK (provider IN ('google', 'microsoft')),

  access_token TEXT NOT NULL,  -- Encrypted via FERNET_KEY
  refresh_token TEXT NOT NULL, -- Encrypted via FERNET_KEY

  client_id TEXT NOT NULL,
  client_secret TEXT NOT NULL,

  scopes TEXT[] NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),

  UNIQUE(user_id, provider)
);

-- Enable RLS
ALTER TABLE user_secrets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users access own secrets"
ON user_secrets FOR ALL
USING (user_id = auth.uid());
```

**Apply Schema:**
```sql
-- Run in Supabase SQL Editor
-- Location: backend/sql/user_secrets.sql
```

---

## RENDER CONFIGURATION

### Backend Service

**Environment Variables:**
```bash
ENV=production
PORT=10000  # Render assigns
BASE_URL=https://intelligent-email-assistant-3e1a.onrender.com

GOOGLE_CLIENT_ID=404491356399-fem39f8euhoffa1jfb341r18rb6ll5pe.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=[secret]
GOOGLE_REDIRECT_URI=https://intelligent-email-assistant-3e1a.onrender.com/auth/callback/google

FRONTEND_URL=https://intelligent-email-frontend.onrender.com

SUPABASE_URL=[your-supabase-url]
SUPABASE_SERVICE_KEY=[your-service-key]

FERNET_KEY=[your-fernet-key]
SESSION_SECRET=[strong-random-string]
```

### Frontend Service

**Environment Variables:**
```bash
VITE_API_BASE_URL=https://intelligent-email-assistant-3e1a.onrender.com
```

**Build Command:**
```bash
npm run build
```

**Start Command:**
```bash
npm run preview
```

---

## COMMON ERRORS & FIXES

### Error: "redirect_uri_mismatch"
**Cause:** Redirect URI in code doesn't match Google Console
**Fix:**
1. Check backend logs for actual redirect_uri sent
2. Copy exact URI (including port and path)
3. Add to Google Console → Authorized redirect URIs
4. Wait 5 minutes for Google to propagate

### Error: "origin_mismatch"
**Cause:** Browser origin not in JavaScript origins list
**Fix:**
1. Check browser URL when clicking "Sign in"
2. Add that exact origin to Google Console → JavaScript origins
3. Remember: No trailing slashes, no paths

### Error: "invalid_client"
**Cause:** GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET wrong
**Fix:**
1. Copy fresh credentials from Google Console
2. Update .env file
3. Restart backend

### Error: "access_denied"
**Cause:** User not in test users list (while in Testing mode)
**Fix:**
1. Google Console → Audience → Test users
2. Add your Gmail address
3. Try OAuth flow again

---

## PRODUCTION DEPLOYMENT CHECKLIST

Before deploying to Render:

- [ ] Update `.env.example` with production template
- [ ] Verify Render environment variables set
- [ ] Apply Supabase `user_secrets` schema
- [ ] Update Google Console redirect URIs with production URLs
- [ ] Test OAuth flow on staging/production
- [ ] Verify encrypted tokens stored in Supabase
- [ ] Check Render logs for OAuth errors
- [ ] Confirm frontend can call authenticated endpoints

---

## SESSION NOTES

**Current Port Situation:**
- Worker testing: Used port 8888 (for testing only)
- OAuth flow: Uses port 8000 (correct for OAuth)
- Production: Uses port 10000 (Render assigns)

**Recommendation:**
- Keep worker testing on 8888 (it has `/healthz` not `/auth/*`)
- Use separate terminal/process for OAuth testing on 8000
- Or: Set `WORKER_MODE=false` to run API mode on 8888

**To Switch Modes:**
```bash
# Worker Mode (port 8888, /healthz endpoint)
export WORKER_MODE=true
python -m backend.src.infrastructure.worker_entry

# API Mode (port 8000, OAuth endpoints)
export WORKER_MODE=false
python -m backend.src.infrastructure.worker_entry
```

---

**Status:** OAuth configuration documented and aligned
**Next Step:** Apply Google Console fixes, then test OAuth flow locally
**Reference:** Keep this file alongside SESSION_STATUS.md for deployment
