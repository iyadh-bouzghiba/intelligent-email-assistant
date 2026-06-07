-- MUI01-R1-C: email_threads account_id NOT NULL enforcement
-- Pre-condition confirmed: zero NULL rows, zero default rows.

ALTER TABLE public.email_threads
  ALTER COLUMN account_id DROP DEFAULT;

ALTER TABLE public.email_threads
  ALTER COLUMN account_id SET NOT NULL;

-- Composite unique index already exists live. Do not recreate.

CREATE INDEX IF NOT EXISTS account_memberships_provider_account_idx
  ON public.account_memberships (provider, account_id);
