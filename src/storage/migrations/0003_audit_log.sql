-- Migration 0003: Audit Log для retention policy
-- Создаёт таблицу для отслеживания удалений

CREATE TABLE IF NOT EXISTS retention_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL,  -- 'DELETE' | 'SOFT_DELETE'
    record_count INTEGER NOT NULL,
    deleted_ids TEXT,  -- JSON array of deleted IDs
    retention_rule TEXT,  -- JSON with rule details
    cutoff_date TIMESTAMP,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dry_run BOOLEAN DEFAULT 0,
    error_message TEXT
);

-- Indexes для performance
CREATE INDEX IF NOT EXISTS idx_audit_table_name ON retention_audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_executed_at ON retention_audit_log(executed_at);

-- Комментарий для документации
-- Эта таблица хранит audit trail всех retention operations:
-- - Что было удалено (table_name)
-- - Сколько записей (record_count)
-- - Какие ID (deleted_ids — JSON array)
-- - Когда (executed_at)
-- - По какому правилу (retention_rule — JSON)
