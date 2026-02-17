-- Migration: Enhance retention_audit_log для production compliance
-- Дата: 2026-02-17
-- Описание: Добавление контекста выполнения, диагностики производительности, безопасности

-- Добавляем новые колонки для идентификации запуска
ALTER TABLE retention_audit_log ADD COLUMN job_run_id TEXT;
ALTER TABLE retention_audit_log ADD COLUMN job_name TEXT DEFAULT 'retention_cleanup';
ALTER TABLE retention_audit_log ADD COLUMN trigger TEXT DEFAULT 'cron'; -- cron|manual|ci|api
ALTER TABLE retention_audit_log ADD COLUMN actor TEXT DEFAULT 'system'; -- system|username|service_account

-- Контекст среды и воспроизводимость
ALTER TABLE retention_audit_log ADD COLUMN environment TEXT; -- dev|staging|prod
ALTER TABLE retention_audit_log ADD COLUMN host TEXT;
ALTER TABLE retention_audit_log ADD COLUMN app_version TEXT;
ALTER TABLE retention_audit_log ADD COLUMN db_schema_version TEXT;

-- Диагностика производительности
ALTER TABLE retention_audit_log ADD COLUMN duration_ms INTEGER;
ALTER TABLE retention_audit_log ADD COLUMN rows_scanned INTEGER; -- Сколько проверили условием

-- Безопасность/масштаб (альтернатива deleted_ids для больших datasets)
ALTER TABLE retention_audit_log ADD COLUMN min_deleted_id INTEGER;
ALTER TABLE retention_audit_log ADD COLUMN max_deleted_id INTEGER;

-- Индексы для диагностики и комплаенса
CREATE INDEX IF NOT EXISTS idx_audit_job_run_id ON retention_audit_log(job_run_id);
CREATE INDEX IF NOT EXISTS idx_audit_environment ON retention_audit_log(environment);
CREATE INDEX IF NOT EXISTS idx_audit_trigger ON retention_audit_log(trigger);
CREATE INDEX IF NOT EXISTS idx_audit_error ON retention_audit_log(error_message) WHERE error_message IS NOT NULL;

-- Комментарии для документации
-- job_run_id: UUID связывает все записи одного запуска retention job
-- trigger: источник запуска (cron = scheduled, manual = CLI, ci = CI/CD, api = API call)
-- actor: кто/что запустило (system, username, service_account)
-- environment: окружение для фильтрации prod logs
-- duration_ms: время выполнения операции (для performance analysis)
-- rows_scanned: сколько записей проверили (vs record_count = сколько удалили)
-- min/max_deleted_id: диапазон ID (для больших datasets вместо полного списка)
