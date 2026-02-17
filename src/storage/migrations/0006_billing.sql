-- Migration 0006: Billing & Freemium
-- Reflexio v2.1 — Surpass Smart Noter Sprint

-- Таблица для отслеживания использования
CREATE TABLE IF NOT EXISTS usage_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    date DATE NOT NULL,
    duration_minutes NUMERIC DEFAULT 0,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_usage_tracking_user_date ON usage_tracking(user_id, date);
CREATE INDEX IF NOT EXISTS idx_usage_tracking_date ON usage_tracking(date);

-- Обновляем user_preferences для premium статуса
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_preferences' AND column_name = 'is_premium'
    ) THEN
        ALTER TABLE user_preferences ADD COLUMN is_premium BOOLEAN DEFAULT false;
        ALTER TABLE user_preferences ADD COLUMN premium_expires_at TIMESTAMPTZ;
    END IF;
END $$;

-- RLS для usage_tracking
ALTER TABLE usage_tracking ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_read_own_usage" ON usage_tracking
    FOR SELECT USING (user_id = auth.uid()::text OR auth.role() = 'service_role');

CREATE POLICY "users_write_own_usage" ON usage_tracking
    FOR ALL USING (user_id = auth.uid()::text OR auth.role() = 'service_role')
    WITH CHECK (user_id = auth.uid()::text OR auth.role() = 'service_role');

-- Комментарии
COMMENT ON TABLE usage_tracking IS 'Отслеживание использования минут пользователями';
COMMENT ON COLUMN user_preferences.is_premium IS 'Статус premium подписки';
COMMENT ON COLUMN user_preferences.premium_expires_at IS 'Дата истечения premium подписки';





