-- Migration 0010: Immutable events — version tracking for structured_events
-- ПОЧЕМУ: INSERT OR REPLACE уничтожал предыдущие версии enrichment.
-- Append-only: старая версия помечается is_current=0, новая вставляется.

-- Новые колонки (идемпотентно — ALTER TABLE ADD COLUMN no-op если существует)
-- SQLite не поддерживает IF NOT EXISTS для ALTER TABLE ADD COLUMN,
-- поэтому ensure_structured_events_table() в ingest_persist.py делает try/except.
-- Эта миграция — формальная запись в schema_migrations для tracking.

-- Partial index: запросы всегда ищут is_current=1
CREATE INDEX IF NOT EXISTS idx_structured_events_current
ON structured_events(transcription_id) WHERE is_current = 1;

-- View: удобный доступ к актуальным версиям
CREATE VIEW IF NOT EXISTS current_events AS
SELECT * FROM structured_events WHERE is_current = 1;
