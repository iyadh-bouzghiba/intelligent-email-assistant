CREATE OR REPLACE FUNCTION public.search_emails_ranked_v3(
    p_account_id     text,
    p_query          text,
    p_limit          integer DEFAULT 200,
    p_has_attachments boolean DEFAULT NULL
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
    has_attachments  boolean,
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
        e.has_attachments,
        ts_rank(e.search_vector, plainto_tsquery('simple', btrim(p_query))) AS rank
    FROM public.emails e
    WHERE
        e.account_id = p_account_id
        AND char_length(btrim(p_query)) >= 2
        AND e.search_vector @@ plainto_tsquery('simple', btrim(p_query))
        AND (p_has_attachments IS NULL OR e.has_attachments = p_has_attachments)
    ORDER BY
        ts_rank(e.search_vector, plainto_tsquery('simple', btrim(p_query))) DESC,
        COALESCE(e.date, e.created_at) DESC
    LIMIT LEAST(GREATEST(COALESCE(p_limit, 50), 1), 200);
$$;
