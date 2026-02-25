-- Migration 0009: social graph — persons, voice samples, voice profiles
-- Supports: Name-Voice Anchor, speaker profile accumulation, KZ GDPR compliance TTL

-- Персоны в социальном окружении пользователя
CREATE TABLE IF NOT EXISTS persons (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    relationship TEXT CHECK(relationship IN
                    ('colleague', 'family', 'friend', 'acquaintance', 'unknown'))
                    DEFAULT 'unknown',
    voice_ready  INTEGER DEFAULT 0,   -- 0/1 (SQLite boolean)
    sample_count INTEGER DEFAULT 0,
    first_seen   TEXT,
    last_seen    TEXT,
    approved_at  TEXT,                -- когда пользователь подтвердил профиль
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);

-- Сырые голосовые сэмплы (накапливаются до подтверждения пользователем)
-- GDPR/KZ compliance: TTL 7 дней для неидентифицированных, 30 дней для pending
CREATE TABLE IF NOT EXISTS person_voice_samples (
    id            TEXT PRIMARY KEY,
    person_name   TEXT,               -- NULL = не идентифицирован
    embedding     BLOB NOT NULL,      -- GE2E d-vector (256 × float32 ≈ 1 KB)
    anchor_conf   REAL DEFAULT 0.0,   -- уверенность якоря 0.0–1.0
    status        TEXT DEFAULT 'accumulating'
                  CHECK(status IN ('accumulating', 'pending_approval', 'approved', 'rejected')),
    source_ingest TEXT,               -- из какой записи
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_voice_samples_person ON person_voice_samples(person_name);
CREATE INDEX IF NOT EXISTS idx_voice_samples_cleanup
    ON person_voice_samples(person_name, status, created_at);

-- Подтверждённые голосовые профили ОКРУЖЕНИЯ (усреднённый d-vector).
-- ПРИМЕЧАНИЕ: voice_profiles (без префикса) уже занята speaker/storage.py
-- для профиля самого пользователя — другая схема, другой lifecycle.
CREATE TABLE IF NOT EXISTS person_voice_profiles (
    person_name    TEXT PRIMARY KEY,
    avg_embedding  BLOB NOT NULL,      -- усреднённый d-vector по всем approved сэмплам
    sample_count   INTEGER NOT NULL,
    avg_confidence REAL NOT NULL,
    approved_at    TEXT NOT NULL,
    expires_at     TEXT NOT NULL       -- approved_at + 365 дней (ежегодное переподтверждение)
);

-- История взаимодействий (рёбра будущего графа)
CREATE TABLE IF NOT EXISTS person_interactions (
    id           TEXT PRIMARY KEY,
    person_name  TEXT NOT NULL REFERENCES persons(name) ON DELETE CASCADE,
    ingest_id    TEXT,
    topics_json  TEXT,                -- JSON array
    emotions_json TEXT,               -- JSON array
    duration_sec REAL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_interactions_person ON person_interactions(person_name);
CREATE INDEX IF NOT EXISTS idx_interactions_date   ON person_interactions(created_at);
