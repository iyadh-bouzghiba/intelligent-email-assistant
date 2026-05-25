-- POLISH01-R1: Add ai_language column to ai_jobs
--
-- Stores the requested output language at job-enqueue time so the worker
-- does not rely on mutable user_preferences at processing time.
--
-- Safe characteristics:
--   - Nullable: existing rows (NULL) trigger legacy fallback in worker.
--   - No DEFAULT required; NULL = "resolve from account preference" (backwards compat).
--   - Idempotent: IF NOT EXISTS guard prevents failure on re-run.
--   - Does not alter the ai_claim_jobs RPC conflict target or unique index.

ALTER TABLE public.ai_jobs
    ADD COLUMN IF NOT EXISTS ai_language TEXT NULL;

COMMENT ON COLUMN public.ai_jobs.ai_language IS
    'Requested output language code (e.g. en, fr, ar). '
    'NULL means the worker resolves language from user_preferences at run time (legacy).';
