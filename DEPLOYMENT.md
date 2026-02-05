# 🚀 DEPLOYMENT GUIDE — INTELLIGENT EMAIL ASSISTANT

**System Status:** Production-Ready
**Security Level:** Enterprise-Grade
**Deployment Platform:** Render
**Estimated Setup Time:** 30 minutes

---

## 📋 PRE-DEPLOYMENT CHECKLIST

Before deploying, ensure you have:

- [ ] GitHub account with repository access
- [ ] Render account (free tier works for testing)
- [ ] Google Cloud Console account (for Gmail OAuth)
- [ ] Azure Portal account (for Outlook OAuth, optional)
- [ ] Supabase account with database created
- [ ] Mistral AI API key

---

## 🔐 STEP 1: VERIFY SYSTEM LOCALLY

Run the verification script to ensure your local environment is configured correctly:

```bash
cd backend
python scripts/verify_system.py
```

**Expected Output:**
```
=== SYSTEM VERIFICATION START ===
[OK] Environment variables present
[OK] Encryption loop verified
[OK] Health endpoint verified (or SKIP if backend not running)
=== SYSTEM READY FOR DEPLOYMENT ===
```

**If any check fails:** Review the error message and fix the configuration before proceeding.

---

## 🌐 STEP 2: RENDER DEPLOYMENT

### 2.1 Connect GitHub Repository

1. Log in to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub account if not already connected
4. Select the `intelligent-email-assistant` repository
5. Render will automatically detect `render.yaml`

### 2.2 Review Services

Render will create two services:

| Service | Type | URL |
|---------|------|-----|
| email-assistant-backend | Web Service | `https://intelligent-email-assistant-3e1a.onrender.com` |
| email-assistant-frontend | Static Site | `https://intelligent-email-frontend.onrender.com` |

### 2.3 Configure Environment Variables

#### Backend Service Environment Variables

In the Render dashboard, navigate to **Backend Service → Environment** and add:

**Critical (Required):**
```bash
FERNET_KEY=REMOVED
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_supabase_service_key_here
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
MISTRAL_API_KEY=your_mistral_api_key_here
```

**Configuration:**
```bash
LOG_LEVEL=INFO
WORKER_MODE=false
LLM_MODE=api
JWT_SECRET_KEY=your_jwt_secret_here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
```

**OAuth URLs (Update with your actual Render URLs):**
```bash
OAUTH_REDIRECT_BASE_URL=https://intelligent-email-assistant-3e1a.onrender.com
BASE_URL=https://intelligent-email-assistant-3e1a.onrender.com
REDIRECT_URI=https://intelligent-email-assistant-3e1a.onrender.com/auth/google/callback
FRONTEND_URL=https://intelligent-email-frontend.onrender.com
```

**Optional (Outlook):**
```bash
OUTLOOK_CLIENT_ID=your_outlook_client_id_here
OUTLOOK_CLIENT_SECRET=your_outlook_client_secret_here
```

#### Frontend Service Environment Variables

Navigate to **Frontend Service → Environment** and add:

```bash
VITE_API_BASE=https://intelligent-email-assistant-3e1a.onrender.com
VITE_SOCKET_URL=https://intelligent-email-assistant-3e1a.onrender.com
```

### 2.4 Deploy

1. Click **"Apply"** to create services
2. Render will build and deploy both services
3. Wait for **"Live"** status (5-10 minutes for first deployment)
4. Check logs for any errors

---

## 🔑 STEP 3: OAUTH PROVIDER SETUP

### 3.1 Google OAuth (Gmail Integration)

#### A. Create OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project or select existing
3. Enable **Gmail API**:
   - Navigate to **APIs & Services → Library**
   - Search for "Gmail API"
   - Click **"Enable"**
4. Create OAuth 2.0 Client ID:
   - Go to **Credentials → Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - Name: `Intelligent Email Assistant`

#### B. Configure Authorized Redirect URIs

Add these redirect URIs:

**Production:**
```
https://intelligent-email-assistant-3e1a.onrender.com/auth/google/callback
```

**Local Development:**
```
http://localhost:8000/auth/google/callback
```

#### C. Save Credentials

1. Copy **Client ID** and **Client Secret**
2. Add them to Render Backend environment variables:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
3. Redeploy backend service

### 3.2 Microsoft OAuth (Outlook Integration) — Optional

#### A. Register Application

1. Go to [Azure Portal](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Click **"New registration"**
3. Name: `Intelligent Email Assistant`
4. Supported account types: **Accounts in any organizational directory and personal Microsoft accounts**
5. Click **"Register"**

#### B. Configure Authentication

1. Navigate to **Authentication → Platform configurations**
2. Click **"Add a platform" → Web**
3. Add redirect URIs:

**Production:**
```
https://intelligent-email-assistant-3e1a.onrender.com/auth/microsoft/callback
```

**Local Development:**
```
http://localhost:8000/auth/microsoft/callback
```

#### C. Create Client Secret

1. Navigate to **Certificates & secrets**
2. Click **"New client secret"**
3. Description: `Render Production`
4. Expiry: **24 months**
5. Click **"Add"**
6. **IMPORTANT:** Copy the secret value immediately (it won't be shown again)

#### D. Save Credentials

Add to Render Backend environment variables:
- `OUTLOOK_CLIENT_ID` (Application ID)
- `OUTLOOK_CLIENT_SECRET` (Client secret value)

---

## 🗄️ STEP 4: SUPABASE DATABASE SETUP

### 4.1 Create Tables

Run these SQL commands in **Supabase SQL Editor**:

```sql
-- Email threads table
CREATE TABLE IF NOT EXISTS email_threads (
    id SERIAL PRIMARY KEY,
    thread_id VARCHAR(255) UNIQUE NOT NULL,
    account_id VARCHAR(255) DEFAULT 'default',
    subject TEXT,
    summary TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Emails table
CREATE TABLE IF NOT EXISTS emails (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) DEFAULT 'primary',
    gmail_message_id VARCHAR(255),
    subject TEXT,
    sender VARCHAR(255),
    date TIMESTAMP,
    body TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, gmail_message_id)
);

-- Optional: Email summaries table
CREATE TABLE IF NOT EXISTS email_summaries (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    thread_id VARCHAR(255) NOT NULL,
    summary TEXT,
    key_points TEXT[],
    action_items TEXT[],
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 Apply Row Level Security (RLS) Policies

Run the RLS policy script:

```bash
# Copy the SQL from backend/scripts/rls_policies.sql
# Paste into Supabase SQL Editor
# Execute the script
```

**Verify RLS is enabled:**

1. Go to **Table Editor** in Supabase
2. Select each table
3. Click **"Security"** tab
4. Verify **"Enable RLS"** is checked
5. Verify policies are listed

### 4.3 Get Supabase Credentials

1. Navigate to **Project Settings → API**
2. Copy:
   - **URL** → `SUPABASE_URL`
   - **service_role key** → `SUPABASE_SERVICE_KEY`
3. Add to Render Backend environment variables

---

## ✅ STEP 5: VALIDATION

### 5.1 Test Backend Health

```bash
curl https://intelligent-email-assistant-3e1a.onrender.com/health
```

**Expected Response:**
```json
{
  "status": "ok"
}
```

### 5.2 Test OAuth Flow

#### Gmail:
1. Visit: `https://intelligent-email-assistant-3e1a.onrender.com/auth/google`
2. You should be redirected to Google login
3. After login, you should be redirected back (check for 200, not 404)
4. Verify in Supabase that tokens are stored (encrypted)

#### Outlook (if configured):
1. Visit: `https://intelligent-email-assistant-3e1a.onrender.com/auth/microsoft`
2. Follow similar steps as Gmail

### 5.3 Test Frontend

1. Visit: `https://intelligent-email-frontend.onrender.com`
2. Open browser console (F12)
3. Check for:
   - ✅ No CORS errors
   - ✅ API connection successful
   - ✅ WebSocket connection established
4. Test email fetching functionality

### 5.4 Run Verification Script in Production

SSH into Render backend (if available) or use Render Shell:

```bash
python backend/scripts/verify_system.py
```

All checks should pass with **[OK]** status.

---

## 🔧 TROUBLESHOOTING

### Backend Won't Start

**Check logs:**
```bash
# In Render Dashboard → Backend Service → Logs
```

**Common issues:**
- Missing environment variable → Add in Render dashboard
- Invalid FERNET_KEY → Regenerate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Database connection failed → Verify Supabase credentials

### Frontend Can't Connect to Backend

**Check:**
1. CORS configuration in backend (FRONTEND_URL must match)
2. VITE_API_BASE is correct (no trailing slash)
3. Backend is actually running (check /health endpoint)

### OAuth Flow Fails

**Verify:**
1. Redirect URIs match exactly (no trailing slashes)
2. OAuth credentials are correct
3. APIs are enabled in Google Cloud Console
4. Environment variables are set in Render

### Tokens Not Decrypting

**Issue:** FERNET_KEY changed or missing

**Solution:**
1. Users must re-authenticate (delete old tokens)
2. Verify FERNET_KEY is consistent across deployments

---

## 📊 MONITORING

### Health Endpoints

- Backend: `https://intelligent-email-assistant-3e1a.onrender.com/health`
- Worker (if enabled): `https://intelligent-email-assistant-3e1a.onrender.com/healthz`

### Logs

Access logs in Render Dashboard:
- Backend Service → Logs
- Frontend Service → Logs

### Supabase Logs

Monitor database queries:
- Supabase Dashboard → Logs → API Logs

---

## 🔄 UPDATES & MAINTENANCE

### Deploying Updates

1. Push code to GitHub:
   ```bash
   git add .
   git commit -m "Update: feature description"
   git push origin main
   ```

2. Render will automatically deploy (if auto-deploy is enabled)

3. Monitor deployment in Render Dashboard

### Rotating Secrets

**FERNET_KEY Rotation (CRITICAL):**

⚠️ **WARNING:** Rotating FERNET_KEY will invalidate all stored tokens. Users must re-authenticate.

1. Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Update FERNET_KEY in Render
3. Clear all tokens from local storage: `data/tenants/default/store.json`
4. Notify users to re-authenticate

**OAuth Secret Rotation:**

1. Generate new credentials in Google Cloud Console / Azure Portal
2. Update environment variables in Render
3. Redeploy backend

---

## 📈 SCALING CONSIDERATIONS

### Current Limits (Free Tier)

- Backend: Spins down after 15 minutes of inactivity
- Cold start: ~30 seconds
- Database: Supabase free tier (500MB)

### Upgrade Recommendations

**For Production:**
1. Upgrade Render to **Starter** plan ($7/month)
   - Removes sleep on inactivity
   - Faster scaling
2. Upgrade Supabase to **Pro** plan ($25/month)
   - More connections
   - Better performance
3. Add monitoring: Sentry, LogRocket, or Datadog

---

## 🆘 SUPPORT & RESOURCES

- **Render Docs:** https://render.com/docs
- **Supabase Docs:** https://supabase.com/docs
- **Google OAuth:** https://developers.google.com/identity/protocols/oauth2
- **Azure OAuth:** https://docs.microsoft.com/en-us/azure/active-directory/develop/

---

## ✅ DEPLOYMENT COMPLETE

**Congratulations!** Your Intelligent Email Assistant is now live.

**Next Steps:**
1. Share frontend URL with users
2. Monitor logs for the first 24 hours
3. Set up automated backups for Supabase
4. Consider adding monitoring and alerting
5. Document any custom configurations

---

**System Status:** 🟢 Production-Ready
**Security Posture:** 🛡️ Enterprise-Grade
**Deployment Date:** [Update this when deployed]
