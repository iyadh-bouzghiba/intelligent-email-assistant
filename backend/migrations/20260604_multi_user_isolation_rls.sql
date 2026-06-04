BEGIN;

ALTER TABLE public.credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_ai_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_intelligence_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role has full access to credentials" ON public.credentials;
DROP POLICY IF EXISTS "Service role has full access to emails" ON public.emails;
DROP POLICY IF EXISTS "Service role has full access to email_ai_summaries" ON public.email_ai_summaries;
DROP POLICY IF EXISTS "Service role has full access to ai_jobs" ON public.ai_jobs;
DROP POLICY IF EXISTS "Service role has full access to user_preferences" ON public.user_preferences;
DROP POLICY IF EXISTS "Service role has full access to account_intelligence_profiles" ON public.account_intelligence_profiles;

DROP POLICY IF EXISTS "Users can only access their own credentials" ON public.credentials;
DROP POLICY IF EXISTS "Users can only access emails from their accounts" ON public.emails;
DROP POLICY IF EXISTS "Users can only access summaries from their accounts" ON public.email_ai_summaries;
DROP POLICY IF EXISTS "Users can only access their ai_jobs" ON public.ai_jobs;

DROP POLICY IF EXISTS "authenticated_select_credentials_by_account" ON public.credentials;
DROP POLICY IF EXISTS "authenticated_insert_credentials_by_account" ON public.credentials;
DROP POLICY IF EXISTS "authenticated_update_credentials_by_account" ON public.credentials;
DROP POLICY IF EXISTS "authenticated_delete_credentials_by_account" ON public.credentials;

DROP POLICY IF EXISTS "authenticated_select_emails_by_account" ON public.emails;
DROP POLICY IF EXISTS "authenticated_insert_emails_by_account" ON public.emails;
DROP POLICY IF EXISTS "authenticated_update_emails_by_account" ON public.emails;
DROP POLICY IF EXISTS "authenticated_delete_emails_by_account" ON public.emails;

DROP POLICY IF EXISTS "authenticated_select_email_ai_summaries_by_account" ON public.email_ai_summaries;
DROP POLICY IF EXISTS "authenticated_insert_email_ai_summaries_by_account" ON public.email_ai_summaries;
DROP POLICY IF EXISTS "authenticated_update_email_ai_summaries_by_account" ON public.email_ai_summaries;
DROP POLICY IF EXISTS "authenticated_delete_email_ai_summaries_by_account" ON public.email_ai_summaries;

DROP POLICY IF EXISTS "authenticated_select_ai_jobs_by_account" ON public.ai_jobs;
DROP POLICY IF EXISTS "authenticated_insert_ai_jobs_by_account" ON public.ai_jobs;
DROP POLICY IF EXISTS "authenticated_update_ai_jobs_by_account" ON public.ai_jobs;
DROP POLICY IF EXISTS "authenticated_delete_ai_jobs_by_account" ON public.ai_jobs;

DROP POLICY IF EXISTS "authenticated_select_user_preferences_by_account" ON public.user_preferences;
DROP POLICY IF EXISTS "authenticated_insert_user_preferences_by_account" ON public.user_preferences;
DROP POLICY IF EXISTS "authenticated_update_user_preferences_by_account" ON public.user_preferences;
DROP POLICY IF EXISTS "authenticated_delete_user_preferences_by_account" ON public.user_preferences;

DROP POLICY IF EXISTS "authenticated_select_account_intelligence_profiles_by_account" ON public.account_intelligence_profiles;
DROP POLICY IF EXISTS "authenticated_insert_account_intelligence_profiles_by_account" ON public.account_intelligence_profiles;
DROP POLICY IF EXISTS "authenticated_update_account_intelligence_profiles_by_account" ON public.account_intelligence_profiles;
DROP POLICY IF EXISTS "authenticated_delete_account_intelligence_profiles_by_account" ON public.account_intelligence_profiles;

CREATE POLICY "Service role has full access to credentials"
ON public.credentials
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role has full access to emails"
ON public.emails
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role has full access to email_ai_summaries"
ON public.email_ai_summaries
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role has full access to ai_jobs"
ON public.ai_jobs
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role has full access to user_preferences"
ON public.user_preferences
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role has full access to account_intelligence_profiles"
ON public.account_intelligence_profiles
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "authenticated_select_credentials_by_account"
ON public.credentials
FOR SELECT
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_insert_credentials_by_account"
ON public.credentials
FOR INSERT
TO authenticated
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_update_credentials_by_account"
ON public.credentials
FOR UPDATE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id)
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_delete_credentials_by_account"
ON public.credentials
FOR DELETE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_select_emails_by_account"
ON public.emails
FOR SELECT
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_insert_emails_by_account"
ON public.emails
FOR INSERT
TO authenticated
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_update_emails_by_account"
ON public.emails
FOR UPDATE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id)
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_delete_emails_by_account"
ON public.emails
FOR DELETE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_select_email_ai_summaries_by_account"
ON public.email_ai_summaries
FOR SELECT
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_insert_email_ai_summaries_by_account"
ON public.email_ai_summaries
FOR INSERT
TO authenticated
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_update_email_ai_summaries_by_account"
ON public.email_ai_summaries
FOR UPDATE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id)
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_delete_email_ai_summaries_by_account"
ON public.email_ai_summaries
FOR DELETE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_select_ai_jobs_by_account"
ON public.ai_jobs
FOR SELECT
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_insert_ai_jobs_by_account"
ON public.ai_jobs
FOR INSERT
TO authenticated
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_update_ai_jobs_by_account"
ON public.ai_jobs
FOR UPDATE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id)
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_delete_ai_jobs_by_account"
ON public.ai_jobs
FOR DELETE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_select_user_preferences_by_account"
ON public.user_preferences
FOR SELECT
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_insert_user_preferences_by_account"
ON public.user_preferences
FOR INSERT
TO authenticated
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_update_user_preferences_by_account"
ON public.user_preferences
FOR UPDATE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id)
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_delete_user_preferences_by_account"
ON public.user_preferences
FOR DELETE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_select_account_intelligence_profiles_by_account"
ON public.account_intelligence_profiles
FOR SELECT
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_insert_account_intelligence_profiles_by_account"
ON public.account_intelligence_profiles
FOR INSERT
TO authenticated
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_update_account_intelligence_profiles_by_account"
ON public.account_intelligence_profiles
FOR UPDATE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id)
WITH CHECK ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

CREATE POLICY "authenticated_delete_account_intelligence_profiles_by_account"
ON public.account_intelligence_profiles
FOR DELETE
TO authenticated
USING ((current_setting('request.jwt.claims', true)::jsonb ->> 'sub') = account_id);

COMMIT;
