-- Reflexio 24/7 Database Schema
-- SQLite schema for MVP

-- Таблица для отслеживания загруженных аудиофайлов
CREATE TABLE IF NOT EXISTS ingest_queue (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingest_status ON ingest_queue(status);
CREATE INDEX IF NOT EXISTS idx_ingest_created ON ingest_queue(created_at);

-- Таблица для транскрипций
CREATE TABLE IF NOT EXISTS transcriptions (
    id TEXT PRIMARY KEY,
    ingest_id TEXT NOT NULL,
    text TEXT NOT NULL,
    language TEXT,
    language_probability REAL,
    duration REAL,
    segments TEXT,  -- JSON массив сегментов
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ingest_id) REFERENCES ingest_queue(id)
);

CREATE INDEX IF NOT EXISTS idx_transcriptions_ingest ON transcriptions(ingest_id);
CREATE INDEX IF NOT EXISTS idx_transcriptions_created ON transcriptions(created_at);

-- Таблица для фактов/событий дня
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    transcription_id TEXT,
    fact_text TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transcription_id) REFERENCES transcriptions(id)
);

CREATE INDEX IF NOT EXISTS idx_facts_timestamp ON facts(timestamp);
CREATE INDEX IF NOT EXISTS idx_facts_transcription ON facts(transcription_id);

-- Таблица для метаданных дайджестов
CREATE TABLE IF NOT EXISTS digests (
    id TEXT PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    content_path TEXT,  -- Путь к .md файлу
    summary TEXT,
    facts_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_digests_date ON digests(date);













