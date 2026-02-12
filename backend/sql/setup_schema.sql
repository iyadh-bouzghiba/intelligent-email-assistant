-- backend/sql/setup_schema.sql
-- Canonical Supabase/Postgres schema bootstrap (idempotent)
-- Required by ControlPlane.verify_schema() and WORKER-PERF-01

-- 0) SCHEMA VERSION (required: schema_version.version + schema_version.applied_at; expected v3)
-- Upgrade-safe: do NOT assume an id column exists.
CREATE TABLE IF NOT EXISTS public.schema_version (
  version TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
  scopes TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Required by upsert(on_conflict="provider,account_id")
CREATE UNIQUE INDEX IF NOT EXISTS credentials_provider_account_uq
ON public.credentials (provider, account_id);

-- 4) THREADS (from DEPLOYMENT.md)
CREATE TABLE IF NOT EXISTS public.email_threads (
  id BIGSERIAL PRIMARY KEY,
  thread_id VARCHAR(255) UNIQUE NOT NULL,
  account_id VARCHAR(255) DEFAULT 'default',
  subject TEXT,
  summary TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 5) EMAILS (from DEPLOYMENT.md; plus dedup index required by ingestion)
CREATE TABLE IF NOT EXISTS public.emails (
  id BIGSERIAL PRIMARY KEY,
  tenant_id VARCHAR(255) DEFAULT 'primary',
  gmail_message_id VARCHAR(255),
  subject TEXT,
  sender VARCHAR(255),
  date TIMESTAMPTZ,
  body TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Ensure dedup contract exists and is consistent with code expectations
CREATE UNIQUE INDEX IF NOT EXISTS emails_tenant_gmail_message_id_uq
ON public.emails (tenant_id, gmail_message_id);

-- 6) EMAIL SUMMARIES (from DEPLOYMENT.md; not required for WORKER-PERF-01 but documented)
CREATE TABLE IF NOT EXISTS public.email_summaries (
  id BIGSERIAL PRIMARY KEY,
  user_id VARCHAR(255) NOT NULL,
  thread_id VARCHAR(255) NOT NULL,
  summary TEXT,
  key_points TEXT[],
  action_items TEXT[],
  confidence_score FLOAT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 7) GMAIL SYNC STATE (required by WORKER-PERF-01 cursor logic)
CREATE TABLE IF NOT EXISTS public.gmail_sync_state (
  tenant_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  last_history_id TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, account_id)
);
