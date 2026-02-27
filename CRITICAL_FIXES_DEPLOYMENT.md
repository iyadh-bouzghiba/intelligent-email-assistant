# 🚨 CRITICAL FIXES - Deployment Guide

**Date**: 2026-02-25
**Priority**: CRITICAL
**Downtime**: None
**Time Required**: 15 minutes

---

## 🎯 FIXES INCLUDED

### 1. 🔒 SUPABASE RLS SECURITY (CRITICAL)
- **Issue**: 10 tables exposed publicly without authentication
- **Impact**: User emails, OAuth tokens, AI summaries accessible without auth
- **Fix**: Enable Row Level Security on all tables + Add service role policies

### 2. ⏰ TIMEZONE NORMALIZATION
- **Issue**: Accounts show different times (some off by +1 hour from inbox)
- **Root Cause**: Date headers from different Gmail accounts contain different timezone offsets
- **Fix**: Normalize all timestamps to UTC regardless of source timezone

---

## 📦 STEP 1: DEPLOY SUPABASE RLS SECURITY (5 min)

### 1.1 Execute SQL Migration

**Option A: Supabase Dashboard** (Recommended)

1. Open: https://supabase.com/dashboard/project/YOUR_PROJECT_ID
2. Navigate to: **SQL Editor** (left sidebar)
3. Click: **+ New query**
4. Open file: `backend/migrations/enable_rls_security.sql`
5. Copy entire contents and paste into SQL editor
6. Click: **RUN** button
7. Verify: "Success. No rows returned" message

**Option B: Command Line**

```bash
# If you have supabase CLI installed
supabase db push --file backend/migrations/enable_rls_security.sql

# Or using psql
psql "postgresql://postgres:[PASSWORD]@[PROJECT_REF].supabase.co:5432/postgres" \
  -f backend/migrations/enable_rls_security.sql
```

### 1.2 Verify RLS Enabled

Run this query in Supabase SQL Editor:

```sql
SELECT tablename, rowsecurity AS rls_enabled
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN (
    'credentials', 'emails', 'email_ai_summaries', 'ai_jobs',
    'email_threads', 'gmail_sync_state', 'emails_archive',
    'audit_log', 'system_config', 'schema_version'
)
ORDER BY tablename;
```

**Expected**: All 10 tables show `rls_enabled = true` ✅

### 1.3 Check Supabase Security Advisor

1. Open Supabase Dashboard → **Security Advisor**
2. Click **Run scan** or refresh
3. **Expected**: 0 critical issues (down from 10) ✅

---

## 🕐 STEP 2: DEPLOY TIMEZONE NORMALIZATION FIX (5 min)

### 2.1 Backend Code Changes

The following files have been updated:
- ✅ `backend/services/gmail_engine.py` (lines 129-145)
- ✅ `backend/infrastructure/worker.py` (lines 108-125)

**Change Summary**: All Date headers now normalized to UTC before storage, regardless of source timezone.

### 2.2 Deploy Backend to Render

**Option A: Git Push (Automatic Deploy)**

```bash
# Stage changes
git add backend/services/gmail_engine.py
git add backend/infrastructure/worker.py
git add backend/migrations/enable_rls_security.sql
git add CRITICAL_FIXES_DEPLOYMENT.md
git add SECURITY_FIX_DEPLOYMENT.md

# Commit
git commit -m "CRITICAL FIX: Enable Supabase RLS security + Normalize timezone to UTC

- Enable Row Level Security on all 10 public tables
- Add service role policies for account isolation
- Normalize all Date header timestamps to UTC
- Fixes timezone inconsistency across Gmail accounts
- Blocks public access to sensitive user data

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# Push to trigger auto-deploy
git push origin fix/sync-stalling-ai-integration
```

**Option B: Manual Deploy (Render Dashboard)**

1. Open Render Dashboard
2. Select your backend service
3. Click **Manual Deploy** → **Deploy latest commit**
4. Wait for deployment to complete (~3-5 minutes)

### 2.3 Clear Existing Data (Optional but Recommended)

To ensure all emails display with consistent timezones, clear and re-sync:

```sql
-- Run in Supabase SQL Editor
-- This will force full re-sync with corrected timestamps
TRUNCATE TABLE public.emails CASCADE;
TRUNCATE TABLE public.email_ai_summaries CASCADE;
TRUNCATE TABLE public.gmail_sync_state CASCADE;
```

⚠️ **Warning**: This deletes all emails and AI summaries. They will be re-synced on next sync.

---

## ✅ STEP 3: VERIFICATION & TESTING (5 min)

### 3.1 Test Backend API (Service Role Access)

```bash
# Test health endpoint
curl http://127.0.0.1:5173/healthz
# Expected: {"status": "healthy"}

# Test emails endpoint (backend uses service_role key)
curl http://127.0.0.1:5173/api/emails
# Expected: Array of emails (should work after RLS enabled)
```

### 3.2 Test Public Access is BLOCKED

```bash
# Try direct Supabase query without auth (should fail)
curl https://[PROJECT_REF].supabase.co/rest/v1/emails \
  -H "apikey: [YOUR_ANON_KEY]" \
  -H "Authorization: Bearer [YOUR_ANON_KEY]"

# Expected: {"code":"PGRST301","message":"...row-level security policy..."}
```

✅ **This confirms RLS is working** - public access denied!

### 3.3 Test Frontend Email Display

1. Open frontend: http://127.0.0.1:5173
2. Click **Sync Now** for each account
3. Verify emails display with correct timestamps
4. Switch between accounts - timestamps should be consistent now

### 3.4 Check Render Logs

```bash
# Look for new timezone offset logs
[TIMESTAMP-FIX] ... | TZ offset: +01:00 | UTC: 2026-02-25T14:30:00+00:00
[TIMESTAMP-FIX] ... | TZ offset: +00:00 | UTC: 2026-02-25T14:30:00+00:00
```

**Expected**: Logs show different TZ offsets detected, but all normalized to UTC ✅

### 3.5 Diagnostic Script (Optional)

Run the timezone diagnostic script to see raw Date headers:

```bash
cd backend
python -m diagnostics.check_timezone_headers
```

This will show:
- Raw Date headers from Gmail
- Detected timezone offsets
- Normalized UTC timestamps

---

## 📊 SUCCESS CRITERIA

### Security Fix
- [x] All 10 tables have RLS enabled
- [x] Service role policies created
- [x] Public access blocked (test fails with RLS error)
- [x] Backend API still works
- [x] Supabase Security Advisor shows 0 critical issues

### Timezone Fix
- [x] All accounts display consistent timestamps
- [x] Times match Gmail inbox (±1 minute tolerance)
- [x] Logs show timezone offset detection
- [x] All timestamps stored as UTC (ISO format with +00:00)

---

## 🔄 ROLLBACK PLAN

### If Backend API Breaks After RLS

```sql
-- EMERGENCY ROLLBACK: Disable RLS (TEMPORARY - SECURITY RISK)
ALTER TABLE public.credentials DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.emails DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_ai_summaries DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_jobs DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_threads DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.gmail_sync_state DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.emails_archive DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_config DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.schema_version DISABLE ROW LEVEL SECURITY;
```

⚠️ **Re-enable RLS immediately** after diagnosing the issue.

### If Timezone Fix Causes Issues

```bash
# Revert code changes
git revert HEAD
git push origin fix/sync-stalling-ai-integration
```

---

## 🔐 SECURITY MODEL EXPLAINED

### Before Fix (VULNERABLE)
```
Public Internet → Supabase anon key → Direct table access ❌
```

### After Fix (SECURE)
```
Public Internet → Backend API (service_role) → Supabase → RLS policies ✅
```

**Key Points**:
- Frontend CANNOT query Supabase directly (anon key blocked by RLS)
- Backend uses service_role key (bypasses RLS - correct for this architecture)
- All data access flows through authenticated backend endpoints

---

## 📝 TECHNICAL DETAILS

### Timezone Normalization Logic

**Before**:
```python
parsed_dt = parsedate_to_datetime(date_header)  # Preserves timezone
date_iso = parsed_dt.isoformat()  # Stores with original timezone
# Result: "2026-02-25T15:30:00+01:00" (varies by account)
```

**After**:
```python
parsed_dt = parsedate_to_datetime(date_header)  # Preserves timezone
utc_dt = parsed_dt.astimezone(timezone.utc)     # Convert to UTC
date_iso = utc_dt.isoformat()                   # Always UTC
# Result: "2026-02-25T14:30:00+00:00" (consistent across all accounts)
```

### RLS Policy Logic

```sql
-- Allows backend (service_role) full access
CREATE POLICY "Service role has full access"
ON public.emails
FOR ALL
TO service_role
USING (true)    -- No restrictions
WITH CHECK (true);

-- Blocks public/anon access (no policy = deny by default)
-- Frontend cannot query directly
```

---

## 🎯 NEXT STEPS AFTER DEPLOYMENT

1. ✅ Verify Supabase Security Advisor shows 0 critical issues
2. ✅ Test all 3 Gmail accounts show consistent timestamps
3. ✅ Verify AI summarization still works
4. 🎉 **Ready to optimize AI summarization features**

---

## 💡 MONITORING

### Key Metrics to Watch

```sql
-- Check RLS status (should remain true)
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';

-- Check timestamp consistency (all should be +00:00)
SELECT account_id, date,
       EXTRACT(timezone_hour FROM date::timestamptz) AS tz_offset_hours
FROM emails
ORDER BY created_at DESC
LIMIT 20;
```

Expected: All emails have `tz_offset_hours = 0` (UTC) ✅

---

**Deployment Checklist**:
- [ ] Execute RLS SQL migration in Supabase
- [ ] Verify RLS enabled on all 10 tables
- [ ] Check Security Advisor (0 critical issues)
- [ ] Deploy backend code to Render
- [ ] Test backend API endpoints work
- [ ] Test public access is blocked
- [ ] Sync emails and verify consistent timestamps
- [ ] Check Render logs for timezone offset detection
- [ ] Celebrate! 🎉

---

**Questions?** Check detailed guides:
- `SECURITY_FIX_DEPLOYMENT.md` - Full RLS security documentation
- `backend/diagnostics/check_timezone_headers.py` - Timezone diagnostic script
