-- BL-00 Gmail-Only Cleanup
-- Purpose:
--   1. Normalise only known-safe legacy Gmail-compatible values to canonical 'gmail':
--        provider = 'google'   (legacy pre-BL-02 label)
--        provider IS NULL      (BL-02 backfill gap)
--        provider = ''         (empty-string gap)
--   2. Replace the BL-02 constraint (gmail|outlook) with a gmail-only constraint
--      on both credentials and emails tables.
--
-- SAFETY CONTRACT:
--   - Only the three known-safe legacy values are normalised.
--   - Any row with an unexpected non-Gmail value (e.g. 'outlook') is NOT silently
--     relabelled. The constraint addition at the end will fail loudly for such rows,
--     preventing silent data corruption.
--   - No tables dropped.
--   - delta_cursor column untouched.
--   - thread_ref column untouched.
--   - Fully idempotent (safe to re-run if migration was partially applied).
--   - Wrapped in a single transaction; any failure rolls back the entire migration.

BEGIN;

-- -------------------------------------------------------------------
-- credentials: normalise known-safe legacy values only
-- -------------------------------------------------------------------

-- 'google' -> 'gmail': the only legacy provider label ever used before BL-02
UPDATE public.credentials
SET provider = 'gmail'
WHERE provider = 'google';

-- NULL -> 'gmail': gaps from before provider column was made NOT NULL
UPDATE public.credentials
SET provider = 'gmail'
WHERE provider IS NULL;

-- '' -> 'gmail': empty-string gaps from the same era
UPDATE public.credentials
SET provider = 'gmail'
WHERE provider = '';

-- -------------------------------------------------------------------
-- credentials: replace BL-02 constraint (gmail|outlook) with gmail-only
-- If unexpected non-gmail rows remain, the ADD CONSTRAINT will fail
-- and the transaction rolls back — intentional loud failure.
-- -------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'credentials_provider_chk'
  ) THEN
    ALTER TABLE public.credentials DROP CONSTRAINT credentials_provider_chk;
  END IF;
END
$$;

ALTER TABLE public.credentials
  ADD CONSTRAINT credentials_provider_chk
  CHECK (provider IN ('gmail'));

-- -------------------------------------------------------------------
-- emails: normalise known-safe legacy values only
-- -------------------------------------------------------------------

UPDATE public.emails
SET provider = 'gmail'
WHERE provider = 'google';

UPDATE public.emails
SET provider = 'gmail'
WHERE provider IS NULL;

UPDATE public.emails
SET provider = 'gmail'
WHERE provider = '';

-- -------------------------------------------------------------------
-- emails: replace BL-02 constraint (gmail|outlook) with gmail-only
-- Same loud-failure contract as credentials above.
-- -------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'emails_provider_chk'
  ) THEN
    ALTER TABLE public.emails DROP CONSTRAINT emails_provider_chk;
  END IF;
END
$$;

ALTER TABLE public.emails
  ADD CONSTRAINT emails_provider_chk
  CHECK (provider IN ('gmail'));

COMMIT;

-- -------------------------------------------------------------------
-- Verification queries (run manually in Supabase SQL Editor after applying)
-- -------------------------------------------------------------------
-- SELECT provider, COUNT(*) FROM public.credentials GROUP BY provider ORDER BY provider;
-- SELECT provider, COUNT(*) FROM public.emails        GROUP BY provider ORDER BY provider;
-- -- Both must return exactly one row: gmail | <n>
-- SELECT COUNT(*) AS non_gmail_credentials FROM public.credentials WHERE provider != 'gmail';
-- SELECT COUNT(*) AS non_gmail_emails       FROM public.emails        WHERE provider != 'gmail';
-- -- Both must return 0.
