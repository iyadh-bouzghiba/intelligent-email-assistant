-- ============================================================================
-- CRITICAL SECURITY FIX: Enable Row Level Security (RLS) on All Public Tables
-- ============================================================================
-- Issue: 10 tables exposed publicly without authentication/authorization
-- Solution: Enable RLS + Add account-based isolation policies
-- Date: 2026-02-25
-- ============================================================================

-- PHASE 1: Enable RLS on All Tables
-- ============================================================================

ALTER TABLE public.credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_ai_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gmail_sync_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emails_archive ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schema_version ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- PHASE 2: Create Security Policies (Account-Based Isolation)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. CREDENTIALS TABLE (Most Sensitive - OAuth Tokens)
-- ----------------------------------------------------------------------------
-- Policy: Users can only access credentials for accounts they own
-- Note: In production, this should be tied to auth.users() JWT claims

-- For now, using service role bypass (backend has full access)
CREATE POLICY "Service role has full access to credentials"
ON public.credentials
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- For authenticated users, restrict to their account_id
-- TODO: Add auth.uid() -> account_id mapping table when implementing user auth
CREATE POLICY "Users can only access their own credentials"
ON public.credentials
FOR SELECT
TO authenticated
USING (false); -- Disabled until user auth is implemented

-- ----------------------------------------------------------------------------
-- 2. EMAILS TABLE (User Email Data)
-- ----------------------------------------------------------------------------
-- Policy: Account-based isolation via account_id column

CREATE POLICY "Service role has full access to emails"
ON public.emails
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Future: When implementing user auth, add account_id -> user mapping
CREATE POLICY "Users can only access emails from their accounts"
ON public.emails
FOR SELECT
TO authenticated
USING (false); -- Disabled until user auth

-- ----------------------------------------------------------------------------
-- 3. EMAIL_AI_SUMMARIES TABLE (AI-Generated Content)
-- ----------------------------------------------------------------------------

CREATE POLICY "Service role has full access to email_ai_summaries"
ON public.email_ai_summaries
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can only access summaries from their accounts"
ON public.email_ai_summaries
FOR SELECT
TO authenticated
USING (false); -- Disabled until user auth

-- ----------------------------------------------------------------------------
-- 4. AI_JOBS TABLE (Background Job Queue)
-- ----------------------------------------------------------------------------

CREATE POLICY "Service role has full access to ai_jobs"
ON public.ai_jobs
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can only access their ai_jobs"
ON public.ai_jobs
FOR SELECT
TO authenticated
USING (false); -- Disabled until user auth

-- ----------------------------------------------------------------------------
-- 5. EMAIL_THREADS TABLE (Conversation Grouping)
-- ----------------------------------------------------------------------------

CREATE POLICY "Service role has full access to email_threads"
ON public.email_threads
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can only access their email_threads"
ON public.email_threads
FOR SELECT
TO authenticated
USING (false); -- Disabled until user auth

-- ----------------------------------------------------------------------------
-- 6. GMAIL_SYNC_STATE TABLE (OAuth Cursor Tracking)
-- ----------------------------------------------------------------------------

CREATE POLICY "Service role has full access to gmail_sync_state"
ON public.gmail_sync_state
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can only access their sync state"
ON public.gmail_sync_state
FOR SELECT
TO authenticated
USING (false); -- Disabled until user auth

-- ----------------------------------------------------------------------------
-- 7. EMAILS_ARCHIVE TABLE (Deleted/Archived Emails)
-- ----------------------------------------------------------------------------

CREATE POLICY "Service role has full access to emails_archive"
ON public.emails_archive
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can only access their archived emails"
ON public.emails_archive
FOR SELECT
TO authenticated
USING (false); -- Disabled until user auth

-- ----------------------------------------------------------------------------
-- 8. AUDIT_LOG TABLE (System Activity Log)
-- ----------------------------------------------------------------------------
-- Policy: Admin-only access (sensitive operational data)

CREATE POLICY "Service role has full access to audit_log"
ON public.audit_log
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- No user access to audit logs (admin-only via service role)

-- ----------------------------------------------------------------------------
-- 9. SYSTEM_CONFIG TABLE (Application Configuration)
-- ----------------------------------------------------------------------------
-- Policy: Read-only for authenticated users, full access for service role

CREATE POLICY "Service role has full access to system_config"
ON public.system_config
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Authenticated users can read system_config"
ON public.system_config
FOR SELECT
TO authenticated
USING (true); -- Allow read-only access to app config

-- ----------------------------------------------------------------------------
-- 10. SCHEMA_VERSION TABLE (Database Migration Tracking)
-- ----------------------------------------------------------------------------
-- Policy: Service role only (infrastructure management)

CREATE POLICY "Service role has full access to schema_version"
ON public.schema_version
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- No user access (infrastructure table)

-- ============================================================================
-- PHASE 3: Verification Queries
-- ============================================================================

-- Run these queries to verify RLS is enabled:
--
-- SELECT schemaname, tablename, rowsecurity
-- FROM pg_tables
-- WHERE schemaname = 'public'
-- AND tablename IN (
--     'credentials', 'emails', 'email_ai_summaries', 'ai_jobs',
--     'email_threads', 'gmail_sync_state', 'emails_archive',
--     'audit_log', 'system_config', 'schema_version'
-- )
-- ORDER BY tablename;
--
-- Expected: All 10 tables should have rowsecurity = true

-- List all policies:
-- SELECT schemaname, tablename, policyname, permissive, roles, cmd
-- FROM pg_policies
-- WHERE schemaname = 'public'
-- ORDER BY tablename, policyname;

-- ============================================================================
-- NOTES FOR PRODUCTION DEPLOYMENT
-- ============================================================================
--
-- 1. CURRENT STATE: Service role bypass policies allow backend full access
--    - This is CORRECT for the current architecture (no frontend auth)
--    - Backend uses SUPABASE_SERVICE_ROLE_KEY (full privileges)
--
-- 2. FUTURE: When implementing user authentication:
--    - Create auth.users table with account_id mapping
--    - Replace "USING (false)" policies with proper JWT claims checks
--    - Example: USING (account_id = current_setting('request.jwt.claims')::json->>'account_id')
--
-- 3. SECURITY IMPACT: This migration BLOCKS public/anon access immediately
--    - Only service_role (backend) can access tables
--    - Frontend uses backend API (which has service_role credentials)
--    - No direct public access to Supabase tables
--
-- 4. TESTING: After deployment, verify:
--    - Backend API endpoints still work (service_role has access)
--    - Direct public queries fail (curl/Postman without auth)
--    - Supabase Security Advisor shows 0 critical issues
--
-- ============================================================================
