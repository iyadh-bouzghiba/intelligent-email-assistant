-- DATA-DELETION-01: Atomic user data deletion RPC
-- Deletes all data for a given uid in correct
-- dependency order. Called by DELETE /api/user.
-- audit_log is explicitly excluded — compliance record.

CREATE OR REPLACE FUNCTION
  public.delete_user_data(p_uid UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_accounts text[];
  v_archive_ids text[];
  v_rows_removed integer := 0;
  v_n integer;
BEGIN
  -- Resolve all account_ids for this uid
  SELECT ARRAY_AGG(account_id)
  INTO v_accounts
  FROM account_memberships
  WHERE user_id = p_uid;

  IF v_accounts IS NULL OR
     array_length(v_accounts, 1) = 0 THEN
    RETURN jsonb_build_object(
      'status', 'no_accounts',
      'rows_removed', 0
    );
  END IF;

  -- Collect gmail_message_ids for archive deletion
  SELECT ARRAY_AGG(DISTINCT gmail_message_id)
  INTO v_archive_ids
  FROM emails
  WHERE account_id = ANY(v_accounts)
    AND gmail_message_id IS NOT NULL;

  -- Step 1: ai_jobs
  DELETE FROM ai_jobs
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 2: email_ai_summaries
  DELETE FROM email_ai_summaries
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 3: email_summaries
  DELETE FROM email_summaries
  WHERE user_email = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 4: gmail_sync_state
  DELETE FROM gmail_sync_state
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 5: sent_emails
  DELETE FROM sent_emails
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 6: emails_archive via gmail_message_id
  IF v_archive_ids IS NOT NULL AND
     array_length(v_archive_ids, 1) > 0 THEN
    DELETE FROM emails_archive
    WHERE gmail_message_id = ANY(v_archive_ids);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_rows_removed := v_rows_removed + v_n;
  END IF;

  -- Step 7: emails
  DELETE FROM emails
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 8: email_threads
  DELETE FROM email_threads
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 9: email_templates
  DELETE FROM email_templates
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 10: user_preferences
  DELETE FROM user_preferences
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 11: account_intelligence_profiles
  DELETE FROM account_intelligence_profiles
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 12: credentials
  DELETE FROM credentials
  WHERE account_id = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 13: user_secrets
  DELETE FROM user_secrets
  WHERE user_email = ANY(v_accounts);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 14: account_memberships
  DELETE FROM account_memberships
  WHERE user_id = p_uid;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  -- Step 15: app_users (FK cascade as safety net)
  DELETE FROM app_users WHERE id = p_uid;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_rows_removed := v_rows_removed + v_n;

  RETURN jsonb_build_object(
    'status', 'deleted',
    'accounts_removed', array_length(v_accounts, 1),
    'rows_removed', v_rows_removed
  );
END;
$$;

-- Revoke public execute. Backend uses service-role.
REVOKE EXECUTE ON FUNCTION
  public.delete_user_data(UUID) FROM PUBLIC;
