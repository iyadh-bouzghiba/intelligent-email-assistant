-- ebaq_01: add per-account AI priority profile storage
ALTER TABLE public.user_preferences
  ADD COLUMN IF NOT EXISTS ai_priority_profile JSONB;
