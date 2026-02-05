-- Migration 0002: Additional indexes for performance
-- PostgreSQL/Supabase version

-- Full-text search indexes (GIN для JSONB и tsvector)
CREATE INDEX IF NOT EXISTS idx_transcriptions_text_search ON transcriptions USING gin(to_tsvector('russian', text));
CREATE INDEX IF NOT EXISTS idx_facts_text_search ON facts USING gin(to_tsvector('russian', fact_text));
CREATE INDEX IF NOT EXISTS idx_claims_text_search ON claims USING gin(to_tsvector('russian', claim_text));

-- Composite indexes для частых запросов
CREATE INDEX IF NOT EXISTS idx_facts_timestamp_confidence ON facts(timestamp DESC, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_claims_validated_confidence ON claims(validated, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_ingest_status_created ON ingest_queue(status, created_at DESC);

-- Partial indexes для оптимизации
CREATE INDEX IF NOT EXISTS idx_ingest_pending ON ingest_queue(created_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_claims_validated_high_confidence ON claims(confidence DESC) WHERE validated = true;







