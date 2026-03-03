-- 0012: Acoustic features for emotion-aware enrichment
-- Добавляет акустические фичи в structured_events.
-- Извлекаются из WAV перед удалением (zero-retention сохраняется).
-- ПОЧЕМУ без ALTER TABLE: _ensure_structured_events_table уже добавляет
-- эти колонки идемпотентно через try/except. Миграция фиксирует факт.
SELECT 1;
