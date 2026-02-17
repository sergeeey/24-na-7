-- Migration 0007: Referrals System
-- Reflexio v2.1 — Surpass Smart Noter Sprint

-- Таблица для referral кодов
CREATE TABLE IF NOT EXISTS referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    invites_count INTEGER DEFAULT 0,
    bonus_applied BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(code);

-- Таблица для использования referral кодов
CREATE TABLE IF NOT EXISTS referral_uses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL,
    user_id TEXT NOT NULL,
    referrer_id TEXT NOT NULL,
    used_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(code, user_id)
);

CREATE INDEX IF NOT EXISTS idx_referral_uses_code ON referral_uses(code);
CREATE INDEX IF NOT EXISTS idx_referral_uses_user ON referral_uses(user_id);
CREATE INDEX IF NOT EXISTS idx_referral_uses_referrer ON referral_uses(referrer_id);

-- RLS для referrals
ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_uses ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_read_own_referrals" ON referrals
    FOR SELECT USING (referrer_id = auth.uid()::text OR auth.role() = 'service_role');

CREATE POLICY "users_read_own_referral_uses" ON referral_uses
    FOR SELECT USING (user_id = auth.uid()::text OR referrer_id = auth.uid()::text OR auth.role() = 'service_role');

CREATE POLICY "service_insert_referrals" ON referrals
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_insert_referral_uses" ON referral_uses
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- Комментарии
COMMENT ON TABLE referrals IS 'Referral коды пользователей';
COMMENT ON TABLE referral_uses IS 'Использование referral кодов';





