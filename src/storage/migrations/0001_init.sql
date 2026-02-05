-- Migration 0001: Initial schema for Reflexio 24/7
-- PostgreSQL/Supabase version

-- Расширение для UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Расширение для векторов (pgvector, если установлено)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Таблица для метаданных аудио
CREATE TABLE IF NOT EXISTS audio_meta (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT,
    duration NUMERIC,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audio_meta_created ON audio_meta(created_at);
CREATE INDEX IF NOT EXISTS idx_audio_meta_source ON audio_meta(source);

-- Таблица для текстовых записей (с embeddings)
CREATE TABLE IF NOT EXISTS text_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id UUID,
    content TEXT NOT NULL,
    embedding vector(1536),  -- Для pgvector (если установлено, иначе можно закомментировать)
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_text_entries_mission ON text_entries(mission_id);
CREATE INDEX IF NOT EXISTS idx_text_entries_created ON text_entries(created_at);
-- CREATE INDEX IF NOT EXISTS idx_text_entries_embedding ON text_entries USING ivfflat (embedding vector_cosine_ops);

-- Таблица для инсайтов
CREATE TABLE IF NOT EXISTS insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    summary TEXT,
    confidence NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_insights_confidence ON insights(confidence);
CREATE INDEX IF NOT EXISTS idx_insights_created ON insights(created_at);

-- Таблица для утверждений (claims)
CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url TEXT,
    claim_text TEXT NOT NULL,
    confidence NUMERIC DEFAULT 0.5,
    validated BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_claims_confidence ON claims(confidence);
CREATE INDEX IF NOT EXISTS idx_claims_validated ON claims(validated);
CREATE INDEX IF NOT EXISTS idx_claims_created ON claims(created_at);

-- Таблица для миссий
CREATE TABLE IF NOT EXISTS missions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    parameters JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_created ON missions(created_at);

-- Таблица для метрик
CREATE TABLE IF NOT EXISTS metrics (
    id SERIAL PRIMARY KEY,
    metric_name TEXT NOT NULL,
    metric_value NUMERIC,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_updated ON metrics(updated_at);

-- Совместимость со старой схемой (для миграции)
CREATE TABLE IF NOT EXISTS ingest_queue (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS transcriptions (
    id TEXT PRIMARY KEY,
    ingest_id TEXT NOT NULL,
    text TEXT NOT NULL,
    language TEXT,
    language_probability REAL,
    duration REAL,
    segments JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    transcription_id TEXT,
    fact_text TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    confidence REAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS digests (
    id TEXT PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    content_path TEXT,
    summary TEXT,
    facts_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

