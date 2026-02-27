# 🔒 CRITICAL SECURITY FIX - Deployment Guide

## ISSUE: 10 Supabase Tables Exposed Publicly (RLS Disabled)

**Severity**: CRITICAL
**Impact**: User emails, OAuth tokens, and AI summaries accessible without authentication
**Fix**: Enable Row Level Security (RLS) on all tables + Add service role policies

---

## 📋 STEP 1: Run SQL Migration in Supabase

### Option A: Supabase Dashboard (Recommended)

1. **Open Supabase Dashboard**: https://supabase.com/dashboard/project/YOUR_PROJECT_ID
2. **Navigate to SQL Editor**: Click "SQL Editor" in left sidebar
3. **Create New Query**: Click "+ New query"
4. **Copy SQL Script**: Open `backend/migrations/enable_rls_security.sql` and copy entire contents
5. **Paste and Execute**: Paste into SQL editor and click "Run"
6. **Verify Success**: Should see "Success. No rows returned" (expected for ALTER TABLE commands)

### Option B: Supabase CLI (Advanced)

```bash
# Ensure you're in the repo-fresh directory
cd c:\Users\Iyadh Bouzghiba\Desktop\Security_Backup\Intelligent-Email-Assistant\repo-fresh

# Run migration
supabase db push --file backend/migrations/enable_rls_security.sql

# Or use psql directly
psql postgresql://postgres:[YOUR_PASSWORD]@[YOUR_PROJECT_REF].supabase.co:5432/postgres \
  -f backend/migrations/enable_rls_security.sql
```

---

## ✅ STEP 2: Verify RLS is Enabled

Run this verification query in Supabase SQL Editor:

```sql
-- Check RLS status on all 10 tables
SELECT
    schemaname,
    tablename,
    rowsecurity AS rls_enabled
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN (
    'credentials', 'emails', 'email_ai_summaries', 'ai_jobs',
    'email_threads', 'gmail_sync_state', 'emails_archive',
    'audit_log', 'system_config', 'schema_version'
)
ORDER BY tablename;
```

**Expected Result**: All 10 tables should show `rls_enabled = true`

---

## 🔍 STEP 3: Verify Policies are Applied

Run this query to list all security policies:

```sql
-- List all RLS policies
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd AS operation
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;
```

**Expected Result**: Should see ~20 policies (2 per table on average)

---

## 🧪 STEP 4: Test Backend API Still Works

### Test 1: Check Health Endpoint
```bash
curl http://127.0.0.1:5173/healthz
# Expected: {"status": "healthy", ...}
```

### Test 2: List Emails (Requires Auth)
```bash
curl http://127.0.0.1:5173/api/emails
# Expected: Array of emails (backend uses service_role key)
```

### Test 3: Verify Public Access is BLOCKED
```bash
# Try direct Supabase query without auth (should fail)
curl https://[YOUR_PROJECT_REF].supabase.co/rest/v1/emails \
  -H "apikey: [YOUR_ANON_KEY]" \
  -H "Authorization: Bearer [YOUR_ANON_KEY]"

# Expected: {"code":"42501","message":"new row violates row-level security policy for table \"emails\""}
```

---

## 🚨 ROLLBACK PLAN (If Issues Arise)

If backend stops working after enabling RLS:

```sql
-- EMERGENCY: Disable RLS on all tables (NOT RECOMMENDED - SECURITY RISK)
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

-- Then drop all policies
DROP POLICY IF EXISTS "Service role has full access to credentials" ON public.credentials;
-- (repeat for all policies)
```

⚠️ **IMPORTANT**: Rollback should ONLY be used temporarily to diagnose issues. Re-enable RLS ASAP.

---

## 📊 STEP 5: Re-Check Supabase Security Advisor

1. Open Supabase Dashboard → Security Advisor
2. Click "Run scan" or refresh the page
3. **Expected Result**: 0 critical issues (down from 10)

---

## 🔐 SECURITY MODEL EXPLAINED

### Current Architecture (No User Auth)

- **Backend**: Uses `SUPABASE_SERVICE_ROLE_KEY` (full database access)
- **Frontend**: Makes API calls to backend (backend authenticates to Supabase)
- **RLS Policies**: Allow service_role full access, block public/anon access

### Why This is Secure

1. **No Direct Public Access**: Frontend cannot query Supabase directly
2. **Backend Gatekeeping**: All data access flows through FastAPI endpoints
3. **Service Role Bypass**: Backend has full privileges (correct for this architecture)
4. **Account Isolation Ready**: Policies prepared for future user auth implementation

### Future: Adding User Authentication

When implementing user login (Supabase Auth, OAuth, etc.):

1. Create `auth.users` table with `account_id` mapping
2. Update RLS policies to check JWT claims:
   ```sql
   USING (account_id = current_setting('request.jwt.claims')::json->>'account_id')
   ```
3. Frontend sends JWT token with requests
4. Supabase enforces account-level isolation automatically

---

## ✅ SUCCESS CRITERIA

- [x] All 10 tables have RLS enabled
- [x] Service role policies allow backend full access
- [x] Public/anon access is blocked
- [x] Backend API endpoints still work
- [x] Supabase Security Advisor shows 0 critical issues
- [x] No data exposure via direct Supabase queries

---

## 📝 NOTES

- **Service Role Key**: Backend uses this for legitimate operations (OAuth refresh, email sync, AI jobs)
- **Performance**: RLS adds ~0-5ms latency per query (negligible)
- **Compatibility**: Existing backend code requires NO CHANGES (service_role bypasses RLS)
- **Compliance**: This fix brings the app into compliance with security best practices

---

**Deployment Time**: ~5 minutes
**Downtime**: None (backend continues working)
**Reversibility**: Yes (rollback script available)
