-- P3 Summary Language Dimension
-- Purpose:
--   Make email_ai_summaries language-aware so that French / Arabic variants
--   of a summary can coexist with the English variant for the same message.
--
-- Safe to apply on a live table:
--   ADD COLUMN ... NOT NULL DEFAULT 'en'  backfills existing rows to 'en'
--   before Postgres enforces NOT NULL, so no row is left null.
--
-- VERIFY BEFORE RUNNING:
--   Confirm the existing unique index name by running:
--     SELECT indexname FROM pg_indexes
--     WHERE tablename = 'email_ai_summaries'
--       AND indexdef LIKE '%account_id%gmail_message_id%prompt_version%';
--   The expected name from setup_schema.sql is: email_ai_summaries_uq
--   If the name differs in your environment, update the DROP INDEX below.

-- Step 1: Add the summary_language column.
-- NOT NULL DEFAULT 'en' is safe: Postgres fills the default for all existing
-- rows atomically before the constraint is checked.
ALTER TABLE public.email_ai_summaries
  ADD COLUMN IF NOT EXISTS summary_language TEXT NOT NULL DEFAULT 'en';

-- Step 2: Drop the old language-blind unique index.
-- Name 'email_ai_summaries_uq' is from setup_schema.sql; verify above before running.
DROP INDEX IF EXISTS public.email_ai_summaries_uq;

-- Step 3: Create the new language-aware unique index.
-- This is the conflict target used by upsert:
--   on_conflict="account_id,gmail_message_id,prompt_version,summary_language"
-- It allows one row per language variant per message per prompt version.
-- The table primary key (id UUID) is unchanged.
CREATE UNIQUE INDEX IF NOT EXISTS email_ai_summaries_uq
ON public.email_ai_summaries (account_id, gmail_message_id, prompt_version, summary_language);
