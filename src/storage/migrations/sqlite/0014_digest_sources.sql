-- 0014: Data lineage для дайджестов
-- ПОЧЕМУ: сейчас дайджест — чёрный ящик. Нельзя проверить на основе каких
-- транскрипций построен вывод. digest_sources раскрывает lineage:
-- "этот инсайт про стресс → основан на 47 сегментах из 12:00-15:00".
-- Важно для GDPR cascading delete: удаляем user data → удаляем все дайджесты,
-- которые использовали эти транскрипции.

CREATE TABLE IF NOT EXISTS digest_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT    NOT NULL,
    transcription_id TEXT   NOT NULL,
    ingest_id        TEXT,
    created_at       TEXT   DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_digest_sources_date ON digest_sources(date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_digest_sources_uniq ON digest_sources(date, transcription_id);
