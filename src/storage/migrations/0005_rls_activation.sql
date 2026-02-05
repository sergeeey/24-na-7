-- Migration 0005: RLS Activation (tenant_id == auth.uid())
-- Reflexio v2.1 — Surpass Smart Noter Sprint

-- Добавляем tenant_id в таблицы если его нет
DO $$
BEGIN
    -- Проверяем и добавляем tenant_id в audio_meta
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'audio_meta' AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE audio_meta ADD COLUMN tenant_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_audio_meta_tenant_id ON audio_meta(tenant_id);
    END IF;
    
    -- Проверяем и добавляем tenant_id в text_entries
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'text_entries' AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE text_entries ADD COLUMN tenant_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_text_entries_tenant_id ON text_entries(tenant_id);
    END IF;
    
    -- Проверяем и добавляем tenant_id в transcriptions (если таблица существует)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'transcriptions') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'transcriptions' AND column_name = 'tenant_id'
        ) THEN
            ALTER TABLE transcriptions ADD COLUMN tenant_id TEXT;
            CREATE INDEX IF NOT EXISTS idx_transcriptions_tenant_id ON transcriptions(tenant_id);
        END IF;
    END IF;
END $$;

-- Обновляем RLS политики для tenant_id == auth.uid()
-- Удаляем старые политики если они есть
DROP POLICY IF EXISTS "users_read_own_data" ON audio_meta;
DROP POLICY IF EXISTS "users_write_own_data" ON audio_meta;
DROP POLICY IF EXISTS "users_read_own_data" ON text_entries;
DROP POLICY IF EXISTS "users_write_own_data" ON text_entries;
DROP POLICY IF EXISTS "users_read_own_data" ON transcriptions;
DROP POLICY IF EXISTS "users_write_own_data" ON transcriptions;

-- Создаём новые политики с tenant_id
CREATE POLICY "users_read_own_data" ON audio_meta
    FOR SELECT USING (tenant_id = auth.uid()::text OR auth.role() = 'service_role');

CREATE POLICY "users_write_own_data" ON audio_meta
    FOR ALL USING (tenant_id = auth.uid()::text OR auth.role() = 'service_role')
    WITH CHECK (tenant_id = auth.uid()::text OR auth.role() = 'service_role');

CREATE POLICY "users_read_own_data" ON text_entries
    FOR SELECT USING (tenant_id = auth.uid()::text OR auth.role() = 'service_role');

CREATE POLICY "users_write_own_data" ON text_entries
    FOR ALL USING (tenant_id = auth.uid()::text OR auth.role() = 'service_role')
    WITH CHECK (tenant_id = auth.uid()::text OR auth.role() = 'service_role');

-- Для transcriptions (если таблица существует)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'transcriptions') THEN
        EXECUTE 'CREATE POLICY IF NOT EXISTS "users_read_own_data" ON transcriptions
            FOR SELECT USING (tenant_id = auth.uid()::text OR auth.role() = ''service_role'')';
        
        EXECUTE 'CREATE POLICY IF NOT EXISTS "users_write_own_data" ON transcriptions
            FOR ALL USING (tenant_id = auth.uid()::text OR auth.role() = ''service_role'')
            WITH CHECK (tenant_id = auth.uid()::text OR auth.role() = ''service_role'')';
    END IF;
END $$;

-- Комментарии
COMMENT ON COLUMN audio_meta.tenant_id IS 'ID пользователя (tenant) для RLS';
COMMENT ON COLUMN text_entries.tenant_id IS 'ID пользователя (tenant) для RLS';





