-- MUI01-R1-B: app_users and account_memberships tables
-- Idempotent, production-safe. Apply via Supabase SQL editor.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ─── Tables ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.app_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.account_memberships (
  user_id UUID NOT NULL REFERENCES public.app_users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL DEFAULT 'gmail',
  account_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, provider, account_id)
);

-- ─── Row Level Security ───────────────────────────────────────────────────────

ALTER TABLE public.app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_memberships ENABLE ROW LEVEL SECURITY;

-- ─── Policies (idempotent via DO blocks) ─────────────────────────────────────

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'app_users'
      AND policyname = 'app_users_service_role_all'
  ) THEN
    CREATE POLICY app_users_service_role_all
      ON public.app_users
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'account_memberships'
      AND policyname = 'account_memberships_service_role_all'
  ) THEN
    CREATE POLICY account_memberships_service_role_all
      ON public.account_memberships
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'app_users'
      AND policyname = 'app_users_authenticated_select_own'
  ) THEN
    CREATE POLICY app_users_authenticated_select_own
      ON public.app_users
      FOR SELECT
      TO authenticated
      USING (id::text = auth.jwt() ->> 'uid');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'account_memberships'
      AND policyname = 'account_memberships_authenticated_select_own'
  ) THEN
    CREATE POLICY account_memberships_authenticated_select_own
      ON public.account_memberships
      FOR SELECT
      TO authenticated
      USING (user_id::text = auth.jwt() ->> 'uid');
  END IF;
END $$;

-- ═══════════════════════════════════════════════════
-- BOOTSTRAP NOTE: This backfill assumes all existing
-- credentials belong to a single owner (the product
-- owner). For production instances with multiple real
-- users, run the generic per-account backfill instead:
--   For each distinct account_id in credentials:
--     INSERT INTO app_users DEFAULT VALUES RETURNING id
--     INSERT INTO account_memberships (user_id, provider,
--       account_id) VALUES (new_id, 'gmail', account_id)
-- ═══════════════════════════════════════════════════

WITH existing_memberships AS (
  SELECT COUNT(*)::int AS membership_count
  FROM public.account_memberships
),
bootstrap_user AS (
  INSERT INTO public.app_users (id)
  SELECT gen_random_uuid()
  WHERE (SELECT membership_count FROM existing_memberships) = 0
    AND EXISTS (
      SELECT 1
      FROM public.credentials
      WHERE provider = 'gmail'
    )
  RETURNING id
),
credential_accounts AS (
  SELECT DISTINCT account_id, provider
  FROM public.credentials
  WHERE provider = 'gmail'
)
INSERT INTO public.account_memberships (
  user_id,
  provider,
  account_id
)
SELECT
  b.id,
  c.provider,
  c.account_id
FROM bootstrap_user b
CROSS JOIN credential_accounts c
ON CONFLICT (user_id, provider, account_id)
DO UPDATE SET updated_at = now();
