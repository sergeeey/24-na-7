-- Migration 0004: User Preferences (opt_out_training flag)
-- Reflexio 24/7 — November 2025 Integration Sprint

-- Таблица для предпочтений пользователя
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL UNIQUE,  -- Можно использовать auth.uid() в Supabase
    preferences JSONB DEFAULT '{}'::jsonb,
    opt_out_training BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_user_preferences_opt_out ON user_preferences(opt_out_training);

-- RLS политики для user_preferences
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_read_own_preferences" ON user_preferences
    FOR SELECT USING (auth.uid()::text = user_id);

CREATE POLICY "users_update_own_preferences" ON user_preferences
    FOR UPDATE USING (auth.uid()::text = user_id);

CREATE POLICY "users_insert_own_preferences" ON user_preferences
    FOR INSERT WITH CHECK (auth.uid()::text = user_id);

-- Комментарии
COMMENT ON TABLE user_preferences IS 'Предпочтения пользователя, включая opt_out_training флаг';
COMMENT ON COLUMN user_preferences.opt_out_training IS 'Флаг отказа от использования данных для обучения';





