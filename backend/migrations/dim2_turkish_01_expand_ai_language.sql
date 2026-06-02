-- backend/migrations/dim2_turkish_01_expand_ai_language.sql
-- DIM2-TURKISH-01: Expand ai_language CHECK constraint to include Turkish (tr).
-- Idempotent: safe to run multiple times against any environment
-- that has the user_preferences table in any valid prior state.

DO $$
BEGIN
  ALTER TABLE public.user_preferences
    DROP CONSTRAINT IF EXISTS user_preferences_ai_language_chk;

  ALTER TABLE public.user_preferences
    ADD CONSTRAINT user_preferences_ai_language_chk
    CHECK (ai_language IN ('en', 'de', 'fr', 'es', 'pt-BR', 'tr', 'ar', 'zh', 'ja', 'ko'));

EXCEPTION
  WHEN duplicate_object THEN
    NULL;
END;
$$;
