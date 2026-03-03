-- Migration 0013: Create tables missing from SQLite schema
-- ПОЧЕМУ: 0001-0009 — PostgreSQL миграции, не применяются к SQLite.
-- Эти таблицы нужны для /graph/*, /compliance/*, /health/metrics endpoints.

-- metrics (из 0001, адаптирована для SQLite)
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_updated ON metrics(updated_at);

-- persons (из 0009 — уже SQLite-совместимая)
CREATE TABLE IF NOT EXISTS persons (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    relationship TEXT CHECK(relationship IN
                    ('colleague', 'family', 'friend', 'acquaintance', 'unknown'))
                    DEFAULT 'unknown',
    voice_ready  INTEGER DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    first_seen   TEXT,
    last_seen    TEXT,
    approved_at  TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);

-- person_voice_samples (из 0009)
CREATE TABLE IF NOT EXISTS person_voice_samples (
    id            TEXT PRIMARY KEY,
    person_name   TEXT,
    embedding     BLOB NOT NULL,
    anchor_conf   REAL DEFAULT 0.0,
    status        TEXT DEFAULT 'accumulating'
                  CHECK(status IN ('accumulating', 'pending_approval', 'approved', 'rejected')),
    source_ingest TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_voice_samples_person ON person_voice_samples(person_name);
CREATE INDEX IF NOT EXISTS idx_voice_samples_cleanup
    ON person_voice_samples(person_name, status, created_at);

-- person_voice_profiles (из 0009)
CREATE TABLE IF NOT EXISTS person_voice_profiles (
    person_name    TEXT PRIMARY KEY,
    avg_embedding  BLOB NOT NULL,
    sample_count   INTEGER NOT NULL,
    avg_confidence REAL NOT NULL,
    approved_at    TEXT NOT NULL,
    expires_at     TEXT NOT NULL
);

-- person_interactions (из 0009)
CREATE TABLE IF NOT EXISTS person_interactions (
    id           TEXT PRIMARY KEY,
    person_name  TEXT NOT NULL REFERENCES persons(name) ON DELETE CASCADE,
    ingest_id    TEXT,
    topics_json  TEXT,
    emotions_json TEXT,
    duration_sec REAL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_interactions_person ON person_interactions(person_name);
CREATE INDEX IF NOT EXISTS idx_interactions_date   ON person_interactions(created_at);
