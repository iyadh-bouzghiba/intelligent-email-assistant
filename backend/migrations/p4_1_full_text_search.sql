-- Migration: p4_1_full_text_search.sql
-- Purpose : Add weighted full-text search vector and GIN index to public.emails
--
-- Config rationale
-- ----------------
-- PRIMARY CONFIG = 'simple'
--   The mailbox is multilingual and mixed-script (English, French, Arabic, and others).
--   'simple' tokenises every language without language-specific stemming, making it
--   safe as a single global search field across all scripts.
--   pg_trgm and unaccent are NOT installed on this database and are explicitly excluded.
--
-- 'arabic' config was verified during the P4.1 audit (smoke query confirmed Arabic-only
-- tokens are matched) but was NOT selected as the stored primary vector for v1 because
-- a per-language stored column strategy is out of scope for this iteration.
--
-- This migration is additive and idempotent (IF NOT EXISTS guards on both DDL statements).
-- No existing columns, indexes, or tables are modified.
-- sent_emails and email_ai_summaries are not touched in this step.

ALTER TABLE public.emails
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(subject, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(sender,  '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(body,    '')), 'C')
    ) STORED;

CREATE INDEX IF NOT EXISTS emails_search_vector_gin
    ON public.emails
    USING GIN (search_vector);
