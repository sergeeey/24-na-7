-- Migration 0003: Row-Level Security (RLS) Policies
-- PostgreSQL/Supabase version

-- Включаем RLS для всех таблиц
ALTER TABLE audio_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE text_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE insights ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE metrics ENABLE ROW LEVEL SECURITY;

-- Политики для audio_meta
CREATE POLICY "allow read all" ON audio_meta FOR SELECT USING (true);
CREATE POLICY "allow insert service_role" ON audio_meta FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "allow update service_role" ON audio_meta FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "allow delete service_role" ON audio_meta FOR DELETE USING (auth.role() = 'service_role');

-- Политики для text_entries
CREATE POLICY "allow read all" ON text_entries FOR SELECT USING (true);
CREATE POLICY "allow insert service_role" ON text_entries FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "allow update service_role" ON text_entries FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "allow delete service_role" ON text_entries FOR DELETE USING (auth.role() = 'service_role');

-- Политики для insights
CREATE POLICY "allow read all" ON insights FOR SELECT USING (true);
CREATE POLICY "allow insert service_role" ON insights FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "allow update service_role" ON insights FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "allow delete service_role" ON insights FOR DELETE USING (auth.role() = 'service_role');

-- Политики для claims
CREATE POLICY "allow read all" ON claims FOR SELECT USING (true);
CREATE POLICY "allow insert service_role" ON claims FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "allow update service_role" ON claims FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "allow delete service_role" ON claims FOR DELETE USING (auth.role() = 'service_role');

-- Политики для missions
CREATE POLICY "allow read all" ON missions FOR SELECT USING (true);
CREATE POLICY "allow insert service_role" ON missions FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "allow update service_role" ON missions FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "allow delete service_role" ON missions FOR DELETE USING (auth.role() = 'service_role');

-- Политики для metrics
CREATE POLICY "allow read all" ON metrics FOR SELECT USING (true);
CREATE POLICY "allow insert service_role" ON metrics FOR INSERT WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "allow update service_role" ON metrics FOR UPDATE USING (auth.role() = 'service_role');
CREATE POLICY "allow delete service_role" ON metrics FOR DELETE USING (auth.role() = 'service_role');

-- Комментарии для документирования
COMMENT ON TABLE audio_meta IS 'Метаданные аудио файлов';
COMMENT ON TABLE text_entries IS 'Текстовые записи с embeddings для semantic search';
COMMENT ON TABLE insights IS 'Инсайты и выводы из анализа';
COMMENT ON TABLE claims IS 'Утверждения из OSINT источников';
COMMENT ON TABLE missions IS 'OSINT миссии и их параметры';
COMMENT ON TABLE metrics IS 'Системные метрики и показатели';











