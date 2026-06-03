-- backend/migrations/user_intelligence_state_01_account_intelligence_profiles.sql
-- USER-INTELLIGENCE-STATE-01 Step 2
-- Creates account_intelligence_profiles table and supporting function.

CREATE TABLE IF NOT EXISTS public.account_intelligence_profiles (
  account_id TEXT PRIMARY KEY,
  observed_categories JSONB NOT NULL DEFAULT '{}'::jsonb,
  category_corrections JSONB NOT NULL DEFAULT '[]'::jsonb,
  confidence_calibration JSONB NOT NULL DEFAULT '[]'::jsonb,
  action_item_completion JSONB NOT NULL DEFAULT '[]'::jsonb,
  notification_preferences JSONB NOT NULL DEFAULT '{
    "urgency_escalation_enabled": false,
    "urgency_threshold": "high",
    "action_item_deadline_notifications_enabled": false,
    "action_item_deadline_hours": 24,
    "thread_silence_notifications_enabled": false,
    "thread_silence_hours": 72
  }'::jsonb,
  last_sync_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
  ALTER TABLE public.account_intelligence_profiles
    ADD CONSTRAINT aip_observed_categories_obj_chk
    CHECK (jsonb_typeof(observed_categories) = 'object');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END;
$$;

DO $$
BEGIN
  ALTER TABLE public.account_intelligence_profiles
    ADD CONSTRAINT aip_category_corrections_arr_chk
    CHECK (jsonb_typeof(category_corrections) = 'array');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END;
$$;

DO $$
BEGIN
  ALTER TABLE public.account_intelligence_profiles
    ADD CONSTRAINT aip_confidence_calibration_arr_chk
    CHECK (jsonb_typeof(confidence_calibration) = 'array');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END;
$$;

DO $$
BEGIN
  ALTER TABLE public.account_intelligence_profiles
    ADD CONSTRAINT aip_action_item_completion_arr_chk
    CHECK (jsonb_typeof(action_item_completion) = 'array');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END;
$$;

DO $$
BEGIN
  ALTER TABLE public.account_intelligence_profiles
    ADD CONSTRAINT aip_notification_preferences_obj_chk
    CHECK (jsonb_typeof(notification_preferences) = 'object');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.increment_account_observed_category(
  p_account_id TEXT,
  p_category TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_account_id TEXT;
  v_category TEXT;
BEGIN
  v_account_id := trim(p_account_id);
  IF v_account_id IS NULL OR v_account_id = '' THEN
    RAISE EXCEPTION 'p_account_id must not be blank';
  END IF;

  v_category := trim(p_category);
  IF v_category IS NULL OR v_category = '' THEN
    RETURN;
  END IF;

  INSERT INTO public.account_intelligence_profiles (
    account_id,
    observed_categories,
    last_sync_at,
    updated_at
  )
  VALUES (
    v_account_id,
    jsonb_build_object(v_category, 1),
    now(),
    now()
  )
  ON CONFLICT (account_id) DO UPDATE
    SET observed_categories = jsonb_set(
          COALESCE(public.account_intelligence_profiles.observed_categories, '{}'::jsonb),
          ARRAY[v_category],
          to_jsonb(
            CASE
              WHEN COALESCE(public.account_intelligence_profiles.observed_categories ->> v_category, '') ~ '^[0-9]+$'
                THEN (public.account_intelligence_profiles.observed_categories ->> v_category)::integer + 1
              ELSE 1
            END
          ),
          true
        ),
        last_sync_at = now(),
        updated_at = now();
END;
$$;
