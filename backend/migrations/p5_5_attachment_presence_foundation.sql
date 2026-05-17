-- Migration: p5_5_attachment_presence_foundation.sql
-- Purpose : Introduce has_attachments boolean contract across inbox, sent,
--           atomic-save RPC, and search-ranked RPC.
--
-- Supports both fresh setup and existing production deployments (all ALTER
-- statements use IF NOT EXISTS / CREATE OR REPLACE for full idempotency).
--
-- Changes in this migration
-- --------------------------
-- 1. ADD has_attachments to public.emails
-- 2. Restore canonical schema authority for public.sent_emails
-- 3. ADD has_attachments to public.sent_emails
-- 4. CREATE public.save_email_with_ai_job_v2 (additive — old function untouched)
-- 5. CREATE public.search_emails_ranked_v2   (additive — old function untouched)

-- ── 1. inbox emails ──────────────────────────────────────────────────────────
ALTER TABLE public.emails
  ADD COLUMN IF NOT EXISTS has_attachments boolean NOT NULL DEFAULT false;

-- ── 2. sent_emails canonical authority (idempotent) ──────────────────────────
-- This table was previously created at runtime without documented schema.
-- Re-establishing authority here so fresh and migrated environments both
-- have the column set documented and guarded.
CREATE TABLE IF NOT EXISTS public.sent_emails (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id       TEXT NOT NULL,
  gmail_message_id TEXT NOT NULL,
  thread_id        TEXT,
  to_address       TEXT,
  cc_addresses     TEXT,
  subject          TEXT,
  body_preview     TEXT,
  sent_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  source           TEXT NOT NULL DEFAULT 'app_send',
  has_attachments  boolean NOT NULL DEFAULT false,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS sent_emails_account_message_id_uq
ON public.sent_emails (account_id, gmail_message_id);

CREATE INDEX IF NOT EXISTS idx_sent_emails_account_sent_at
ON public.sent_emails (account_id, sent_at DESC);

-- ── 3. has_attachments on existing sent_emails rows ──────────────────────────
ALTER TABLE public.sent_emails
  ADD COLUMN IF NOT EXISTS has_attachments boolean NOT NULL DEFAULT false;

-- ── 4. Atomic save RPC v2 — additive; old function left untouched ─────────────
CREATE OR REPLACE FUNCTION public.save_email_with_ai_job_v2(
  p_subject         text,
  p_sender          text,
  p_date            timestamptz,
  p_body            text,
  p_message_id      text,
  p_account_id      text,
  p_tenant_id       text,
  p_thread_id       text    DEFAULT NULL,
  p_provider        text    DEFAULT 'gmail',
  p_thread_ref      text    DEFAULT NULL,
  p_create_ai_job   boolean DEFAULT false,
  p_has_attachments boolean DEFAULT false
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_email_id    uuid;
  v_job_id      uuid    := null;
  v_job_existed boolean := false;
BEGIN
  -- Atomic operation 1: Insert/update email
  INSERT INTO emails (
    subject,
    sender,
    date,
    body,
    gmail_message_id,
    account_id,
    tenant_id,
    thread_id,
    provider,
    thread_ref,
    has_attachments,
    created_at,
    updated_at
  )
  VALUES (
    p_subject,
    p_sender,
    p_date,
    p_body,
    p_message_id,
    p_account_id,
    p_tenant_id,
    p_thread_id,
    p_provider,
    COALESCE(p_thread_ref, p_thread_id),
    p_has_attachments,
    now(),
    now()
  )
  ON CONFLICT (account_id, gmail_message_id) DO UPDATE
  SET
    updated_at      = now(),
    thread_id       = COALESCE(EXCLUDED.thread_id,  emails.thread_id),
    provider        = COALESCE(EXCLUDED.provider,   emails.provider),
    thread_ref      = COALESCE(EXCLUDED.thread_ref, emails.thread_ref),
    has_attachments = EXCLUDED.has_attachments
  RETURNING id INTO v_email_id;

  -- Atomic operation 2: Conditionally create AI job (same transaction)
  IF p_create_ai_job THEN
    SELECT id INTO v_job_id
    FROM ai_jobs
    WHERE job_type        = 'email_summarize_v1'
      AND account_id      = p_account_id
      AND gmail_message_id = p_message_id
    LIMIT 1;

    IF v_job_id IS NOT NULL THEN
      v_job_existed := true;
    ELSE
      INSERT INTO ai_jobs (
        job_type,
        account_id,
        gmail_message_id,
        status,
        attempts,
        run_after,
        created_at,
        updated_at
      )
      VALUES (
        'email_summarize_v1',
        p_account_id,
        p_message_id,
        'queued',
        0,
        now(),
        now(),
        now()
      )
      ON CONFLICT (job_type, account_id, gmail_message_id) DO NOTHING
      RETURNING id INTO v_job_id;
    END IF;
  END IF;

  RETURN json_build_object(
    'email_id',   v_email_id,
    'job_id',     v_job_id,
    'job_existed', v_job_existed,
    'job_created', (p_create_ai_job AND v_job_id IS NOT NULL)
  );
END;
$$;

-- ── 5. Search RPC v2 — additive; old function left untouched ──────────────────
CREATE OR REPLACE FUNCTION public.search_emails_ranked_v2(
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
    ORDER BY
        ts_rank(e.search_vector, plainto_tsquery('simple', btrim(p_query))) DESC,
        COALESCE(e.date, e.created_at) DESC
    LIMIT LEAST(GREATEST(COALESCE(p_limit, 50), 1), 200);
$$;
