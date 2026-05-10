-- Migration: p4_1_full_text_search_refine_body_cleanup.sql
-- Purpose : Corrective refinement — rebuild public.emails.search_vector with
--           cleaned body text to remove URL and HTML-entity noise before indexing.
--
-- Why this rebuild is required
-- ----------------------------
-- Quality audit of the initial search_vector (created in p4_1_full_text_search.sql)
-- found that raw body text was indexed without normalisation, causing material pollution:
--   - 75.3 % of rows contain at least one URL (https://, http://, www.)
--   - 0.4 % of rows contain HTML entity tokens (&amp;, &#39;, etc.)
-- URL tokens dominate the 'C'-weight tsvector and dilute semantic signal.
-- M4 vector comparison confirmed the cleaned body vector is dramatically more semantic.
-- M3 comparison showed no observed degradation for sampled keyword results after cleaning.
--
-- Because search_vector is a GENERATED ALWAYS STORED column it cannot be altered
-- in-place; the only safe path is drop-and-recreate of the column (and its index).
-- This migration only affects derived search artifacts (the generated column and the
-- GIN index) — no business data columns are touched.
--
-- Config notes
-- ------------
-- PRIMARY CONFIG remains 'simple' — the mailbox is multilingual and mixed-script
-- (English, French, Arabic, and others).  'simple' is safe across all scripts without
-- language-specific stemming.  pg_trgm and unaccent are not installed and are not used.
-- sent_emails and email_ai_summaries are not touched.

-- Step 1: drop the GIN index (must precede column drop)
DROP INDEX IF EXISTS public.emails_search_vector_gin;

-- Step 2: drop the generated column
ALTER TABLE public.emails DROP COLUMN IF EXISTS search_vector;

-- Step 3: re-add the generated column with normalised body
ALTER TABLE public.emails
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(subject, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(sender,  '')), 'B') ||
        setweight(
            to_tsvector(
                'simple',
                regexp_replace(
                    regexp_replace(
                        regexp_replace(coalesce(body, ''), E'https?://\\S+|www\\.\\S+', ' ', 'gi'),
                        E'&[A-Za-z#0-9]+;', ' ', 'g'
                    ),
                    E'\\s+', ' ', 'g'
                )
            ),
            'C'
        )
    ) STORED;

-- Step 4: recreate the GIN index
CREATE INDEX IF NOT EXISTS emails_search_vector_gin
    ON public.emails
    USING GIN (search_vector);
