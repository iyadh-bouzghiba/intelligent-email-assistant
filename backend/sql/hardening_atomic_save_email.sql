-- Hardening Patch: Atomic Email+Job Save with Cost Control
--
-- Problem: email insert and AI job creation are separate operations
-- If process crashes between them, emails are orphaned (no AI processing)
--
-- Solution: Single RPC function that atomically saves email + conditionally creates AI job
-- Cost control: Caller explicitly passes whether to create AI job (preserves 30-cap)
--
-- Usage:
--   save_email_with_ai_job(..., p_create_ai_job := true)  -- First 30 emails
--   save_email_with_ai_job(..., p_create_ai_job := false) -- Rest

CREATE OR REPLACE FUNCTION public.save_email_with_ai_job(
  p_subject text,
  p_sender text,
  p_date timestamptz,
  p_body text,
  p_message_id text,
  p_account_id text,
  p_tenant_id text,
  p_thread_id text DEFAULT NULL,
  p_create_ai_job boolean DEFAULT false
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_email_id uuid;
  v_job_id uuid := null;
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
    now(),
    now()
  )
  ON CONFLICT (account_id, gmail_message_id) DO UPDATE
  SET
    updated_at = now(),
    thread_id = COALESCE(EXCLUDED.thread_id, emails.thread_id)
  RETURNING id INTO v_email_id;

  -- Atomic operation 2: Conditionally create AI job (same transaction)
  IF p_create_ai_job THEN
    -- Check if job already exists
    SELECT id INTO v_job_id
    FROM ai_jobs
    WHERE job_type = 'email_summarize_v1'
      AND account_id = p_account_id
      AND gmail_message_id = p_message_id
    LIMIT 1;

    IF v_job_id IS NOT NULL THEN
      v_job_existed := true;
    ELSE
      -- Create new job
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

  -- Return result
  RETURN json_build_object(
    'email_id', v_email_id,
    'job_id', v_job_id,
    'job_existed', v_job_existed,
    'job_created', (p_create_ai_job AND v_job_id IS NOT NULL)
  );
END;
$$;

-- Grant execute permission (adjust role as needed)
-- GRANT EXECUTE ON FUNCTION public.save_email_with_ai_job TO authenticated;
