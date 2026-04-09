-- BL-02 Provider Abstraction Foundation
-- Purpose:
--   1. Ensure provider-awareness exists on credentials and emails tables
--   2. Add provider-scoped cursor field on credentials
--   3. Add provider + provider-thread reference fields on emails
--   4. Keep changes idempotent and non-destructive

BEGIN;

-- -------------------------------------------------------------------
-- credentials table hardening / provider foundation
-- -------------------------------------------------------------------
ALTER TABLE public.credentials
  ADD COLUMN IF NOT EXISTS delta_cursor TEXT;

ALTER TABLE public.credentials
  ADD COLUMN IF NOT EXISTS provider TEXT;

UPDATE public.credentials
SET provider = 'gmail'
WHERE provider IS NULL OR provider = '';

ALTER TABLE public.credentials
  ALTER COLUMN provider SET DEFAULT 'gmail';

ALTER TABLE public.credentials
  ALTER COLUMN provider SET NOT NULL;


-- Backfill delta_cursor from legacy gmail_sync_state where available
UPDATE public.credentials c
SET delta_cursor = s.last_history_id
FROM public.gmail_sync_state s
WHERE c.account_id = s.account_id
  AND (c.delta_cursor IS NULL OR c.delta_cursor = '')
  AND s.last_history_id IS NOT NULL;
-- SELECT COUNT(*) AS credentials_missing_delta_cursor FROM public.credentials WHERE delta_cursor IS NULL OR delta_cursor = '';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'credentials_provider_chk'
  ) THEN
    ALTER TABLE public.credentials
      ADD CONSTRAINT credentials_provider_chk
      CHECK (provider IN ('gmail', 'outlook'));
  END IF;
END
$$;

-- -------------------------------------------------------------------
-- emails table provider foundation
-- -------------------------------------------------------------------
ALTER TABLE public.emails
  ADD COLUMN IF NOT EXISTS provider TEXT;

ALTER TABLE public.emails
  ADD COLUMN IF NOT EXISTS thread_ref TEXT;

UPDATE public.emails
SET provider = 'gmail'
WHERE provider IS NULL OR provider = '';

ALTER TABLE public.emails
  ALTER COLUMN provider SET DEFAULT 'gmail';

ALTER TABLE public.emails
  ALTER COLUMN provider SET NOT NULL;

-- Optional backfill from legacy Gmail-native thread_id
UPDATE public.emails
SET thread_ref = thread_id
WHERE thread_ref IS NULL
  AND thread_id IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'emails_provider_chk'
  ) THEN
    ALTER TABLE public.emails
      ADD CONSTRAINT emails_provider_chk
      CHECK (provider IN ('gmail', 'outlook'));
  END IF;
END
$$;

COMMIT;

-- -------------------------------------------------------------------
-- Verification queries (run manually after applying migration)
-- -------------------------------------------------------------------
-- SELECT provider, COUNT(*) FROM public.credentials GROUP BY provider ORDER BY provider;
-- SELECT provider, COUNT(*) FROM public.emails GROUP BY provider ORDER BY provider;
-- SELECT COUNT(*) AS credentials_missing_provider FROM public.credentials WHERE provider IS NULL OR provider = '';
-- SELECT COUNT(*) AS emails_missing_provider FROM public.emails WHERE provider IS NULL OR provider = '';
