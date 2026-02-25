-- Migration 0008: semantic memory + integrity + retrieval traces

CREATE TABLE IF NOT EXISTS integrity_events (
    id TEXT PRIMARY KEY,
    ingest_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    prev_hash TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_integrity_ingest_created
    ON integrity_events(ingest_id, created_at);

CREATE TABLE IF NOT EXISTS memory_nodes (
    id TEXT PRIMARY KEY,
    source_ingest_id TEXT,
    source_transcription_id TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    topics_json JSONB,
    entities_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_nodes_created ON memory_nodes(created_at);
CREATE INDEX IF NOT EXISTS idx_memory_nodes_ingest ON memory_nodes(source_ingest_id);

CREATE TABLE IF NOT EXISTS retrieval_traces (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    node_ids_json JSONB,
    top_k INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_retrieval_traces_created ON retrieval_traces(created_at);
