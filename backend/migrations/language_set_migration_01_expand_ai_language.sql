-- backend/migrations/language_set_migration_01_expand_ai_language.sql
-- LANGUAGE-SET-MIGRATION-01 DIM2: Expand ai_language CHECK constraint
-- from the original set {en, fr, ar}
-- to the DIM2 target set {en, de, fr, es, pt-BR, ar, zh, ja, ko}
--
-- Idempotent: safe to run multiple times against any environment
-- that has the user_preferences table in any valid prior state.

DO $$
BEGIN
  -- Drop the old constraint if it exists (name unchanged by design).
  -- If it does not exist, the EXCEPTION handler silences the error.
  ALTER TABLE public.user_preferences
    DROP CONSTRAINT IF EXISTS user_preferences_ai_language_chk;

  -- Re-add with the expanded DIM2 language set.
  ALTER TABLE public.user_preferences
    ADD CONSTRAINT user_preferences_ai_language_chk
    CHECK (ai_language IN ('en', 'de', 'fr', 'es', 'pt-BR', 'ar', 'zh', 'ja', 'ko'));

EXCEPTION
  WHEN duplicate_object THEN
    NULL; -- constraint already updated; nothing to do
END;
$$;
