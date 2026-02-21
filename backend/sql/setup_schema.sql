-- backend/sql/setup_schema.sql
-- Canonical Supabase/Postgres schema bootstrap (idempotent)
-- Required by ControlPlane.verify_schema() and WORKER-PERF-01

-- 0) SCHEMA VERSION (required: schema_version.version + schema_version.applied_at; expected v3)
-- Upgrade-safe: do NOT assume an id column exists.
CREATE TABLE IF NOT EXISTS public.schema_version (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ DEFAULT now()
);

-- If schema_version already exists but is missing columns, add them.
ALTER TABLE public.schema_version
  ADD COLUMN IF NOT EXISTS version TEXT,
  ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ;

-- Ensure applied_at is usable for ordering
ALTER TABLE public.schema_version
  ALTER COLUMN applied_at SET DEFAULT now();

UPDATE public.schema_version
SET applied_at = now()
WHERE applied_at IS NULL;

-- Ensure v3 can be upserted deterministically
CREATE UNIQUE INDEX IF NOT EXISTS schema_version_version_uq
ON public.schema_version (version);

INSERT INTO public.schema_version (version, applied_at)
VALUES ('v3', now())
ON CONFLICT (version) DO UPDATE
SET applied_at = EXCLUDED.applied_at;

-- 1) SYSTEM CONFIG (required: system_config.key + system_config.value; used by ControlPlane global policy)
CREATE TABLE IF NOT EXISTS public.system_config (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed default policy if missing (fail-open behavior aligns with code defaults)
INSERT INTO public.system_config (key, value, updated_at)
VALUES (
  'global_policy',
  '{
    "worker_enabled": true,
    "max_emails_per_cycle": 50,
    "tenant_quota_enabled": false
  }'::jsonb,
  now()
)
ON CONFLICT (key) DO NOTHING;

-- 2) AUDIT LOG (required by ControlPlane.log_audit)
CREATE TABLE IF NOT EXISTS public.audit_log (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'primary',
  action TEXT NOT NULL,
  resource TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3) OAUTH CREDENTIALS (required by SupabaseStore credentials upsert/select)
CREATE TABLE IF NOT EXISTS public.credentials (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  account_id TEXT NOT NULL,
  encrypted_payload JSONB NOT NULL,
  scopes TEXT DEFAULT '',
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Add columns if they don't exist (upgrade-safe)
ALTER TABLE public.credentials
  ADD COLUMN IF NOT EXISTS provider TEXT,
  ADD COLUMN IF NOT EXISTS account_id TEXT,
  ADD COLUMN IF NOT EXISTS encrypted_payload JSONB,
  ADD COLUMN IF NOT EXISTS scopes TEXT,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

-- Required by upsert(on_conflict="provider,account_id")
CREATE UNIQUE INDEX IF NOT EXISTS credentials_provider_account_uq
ON public.credentials (provider, account_id);

-- 4) THREADS (from DEPLOYMENT.md)
CREATE TABLE IF NOT EXISTS public.email_threads (
  id BIGSERIAL PRIMARY KEY,
  thread_id VARCHAR(255) NOT NULL,
  account_id VARCHAR(255) DEFAULT 'default',
  subject TEXT,
  summary TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Add account_id if it doesn't exist (upgrade-safe)
ALTER TABLE public.email_threads
  ADD COLUMN IF NOT EXISTS account_id VARCHAR(255) DEFAULT 'default';

-- Required unique index on (account_id, thread_id)
CREATE UNIQUE INDEX IF NOT EXISTS email_threads_account_thread_id_uq
ON public.email_threads (account_id, thread_id);

-- Ordering index for multi-account queries
CREATE INDEX IF NOT EXISTS idx_email_threads_account_created
ON public.email_threads (account_id, created_at DESC);

-- 5) EMAILS (from DEPLOYMENT.md; plus dedup index required by ingestion)
CREATE TABLE IF NOT EXISTS public.emails (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject TEXT,
  sender TEXT,
  date TIMESTAMPTZ,
  body TEXT,
  gmail_message_id TEXT,
  tenant_id TEXT DEFAULT 'primary',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMP WITHOUT TIME ZONE,
  account_id TEXT DEFAULT 'default'
);

-- Add columns if they don't exist (upgrade-safe)
ALTER TABLE public.emails
  ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS subject TEXT,
  ADD COLUMN IF NOT EXISTS sender TEXT,
  ADD COLUMN IF NOT EXISTS date TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS body TEXT,
  ADD COLUMN IF NOT EXISTS gmail_message_id TEXT,
  ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'primary',
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE,
  ADD COLUMN IF NOT EXISTS account_id TEXT DEFAULT 'default';

-- Ensure dedup contract exists (account_id, gmail_message_id)
CREATE UNIQUE INDEX IF NOT EXISTS emails_account_gmail_message_id_uq
ON public.emails (account_id, gmail_message_id);

-- Ordering index for queries
CREATE INDEX IF NOT EXISTS idx_emails_created_at
ON public.emails (created_at DESC);

-- 6) EMAIL SUMMARIES (from DEPLOYMENT.md; not required for WORKER-PERF-01 but documented)
CREATE TABLE IF NOT EXISTS public.email_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_email TEXT,
  subject TEXT,
  summary_text TEXT,
  received_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  account_id TEXT
);

-- Add columns if they don't exist (upgrade-safe)
ALTER TABLE public.email_summaries
  ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS user_email TEXT,
  ADD COLUMN IF NOT EXISTS subject TEXT,
  ADD COLUMN IF NOT EXISTS summary_text TEXT,
  ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now(),
  ADD COLUMN IF NOT EXISTS account_id TEXT;

-- 7) GMAIL SYNC STATE (required by WORKER-PERF-01 cursor logic)
CREATE TABLE IF NOT EXISTS public.gmail_sync_state (
  tenant_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  last_history_id TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, account_id)
);

-- 8) AI JOB QUEUE + SUMMARIES (SUMM-SCHEMA-01) — worker-only Mistral pipeline
CREATE TABLE IF NOT EXISTS public.ai_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type TEXT NOT NULL,
  account_id TEXT NOT NULL,
  gmail_message_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', -- queued|running|succeeded|failed|dead
  attempts INT NOT NULL DEFAULT 0,
  run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
  locked_at TIMESTAMPTZ,
  locked_by TEXT,
  last_error_code TEXT,
  last_error_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotent enqueue key: one job per (job_type, account_id, gmail_message_id)
CREATE UNIQUE INDEX IF NOT EXISTS ai_jobs_uq
ON public.ai_jobs (job_type, account_id, gmail_message_id);

-- Efficient polling for workers
CREATE INDEX IF NOT EXISTS ai_jobs_poll_idx
ON public.ai_jobs (status, run_after, created_at);

CREATE TABLE IF NOT EXISTS public.email_ai_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id TEXT NOT NULL,
  gmail_message_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  model TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  summary_json JSONB NOT NULL,
  summary_text TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotent results key: one summary per (account_id, gmail_message_id, prompt_version)
CREATE UNIQUE INDEX IF NOT EXISTS email_ai_summaries_uq
ON public.email_ai_summaries (account_id, gmail_message_id, prompt_version);

CREATE OR REPLACE FUNCTION public.ai_claim_jobs(
  p_job_type text,
  p_limit int,
  p_worker_id text
)
RETURNS SETOF public.ai_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  WITH cte AS (
    SELECT id
    FROM public.ai_jobs
    WHERE job_type = p_job_type
      AND status = 'queued'
      AND run_after <= now()
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT p_limit
  )
  UPDATE public.ai_jobs j
  SET status = 'running',
      locked_at = now(),
      locked_by = p_worker_id,
      updated_at = now()
  FROM cte
  WHERE j.id = cte.id
  RETURNING j.*;
END;
$$;

-- GUARD: Never paste HTML entities into this SQL file. Use raw comparison operators (<=, >=) only.
