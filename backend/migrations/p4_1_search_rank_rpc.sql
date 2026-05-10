-- Migration: p4_1_search_rank_rpc.sql
-- Purpose : Create a minimal read-only PostgreSQL function that returns ranked
--           FTS candidate rows from public.emails for a given account and query.
--
-- Why this function exists
-- ------------------------
-- The Supabase PostgREST table API only accepts plain column names and
-- schema-defined computed columns in SELECT and ORDER BY expressions.
-- It cannot express ts_rank(search_vector, plainto_tsquery('simple', q))
-- with a dynamic runtime argument through the standard .table().select().order()
-- chain used throughout service.py.
--
-- This function resolves that exact blocker for the GET /api/search route in
-- service.py: by wrapping the ts_rank expression inside a STABLE SQL function
-- callable via store.client.rpc('search_emails_ranked', {...}), service.py can
-- retrieve server-ranked candidates without inventing unsupported query syntax.
--
-- Responsibility boundary
-- -----------------------
-- This function returns raw ranked email rows ONLY.
-- service.py retains full responsibility for:
--   - summary enrichment (preferred language / English fallback / newest fallback)
--   - sent_emails activity timestamp merge
--   - thread collapse (thread_id -> gmail_message_id -> subject fallback key)
--   - thread-level unread propagation
--   - final slice to the caller-requested limit
--
-- This function is strictly read-only and candidate-only.
-- Ranking config is 'simple' — matches the stored search_vector config chosen
-- in p4_1_full_text_search.sql for mixed-language, mixed-script mailbox support.

CREATE OR REPLACE FUNCTION public.search_emails_ranked(
    p_account_id text,
    p_query      text,
    p_limit      integer DEFAULT 200
)
RETURNS TABLE (
    id               uuid,
    account_id       text,
    subject          text,
    sender           text,
    date             timestamptz,
    body             text,
    gmail_message_id text,
    thread_id        text,
    tenant_id        text,
    created_at       timestamptz,
    updated_at       timestamp without time zone,
    provider         text,
    thread_ref       text,
    is_read          boolean,
    rank             real
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
    SELECT
        e.id,
        e.account_id,
        e.subject,
        e.sender,
        e.date,
        e.body,
        e.gmail_message_id,
        e.thread_id,
        e.tenant_id,
        e.created_at,
        e.updated_at,
        e.provider,
        e.thread_ref,
        e.is_read,
        ts_rank(e.search_vector, plainto_tsquery('simple', btrim(p_query))) AS rank
    FROM public.emails e
    WHERE
        e.account_id = p_account_id
        AND char_length(btrim(p_query)) >= 2
        AND e.search_vector @@ plainto_tsquery('simple', btrim(p_query))
    ORDER BY
        ts_rank(e.search_vector, plainto_tsquery('simple', btrim(p_query))) DESC,
        COALESCE(e.date, e.created_at) DESC
    LIMIT LEAST(GREATEST(COALESCE(p_limit, 50), 1), 200);
$$;
