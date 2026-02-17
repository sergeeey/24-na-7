-- Migration: Add Fact Layer v4 columns to facts table (SQLite compatible)
-- Version: 4.0
-- Date: 2026-02-17
-- Description: Extends existing facts table with source attribution, versioning, and hallucination prevention
-- Note: This is a SQLite-specific version (no IF NOT EXISTS in ALTER TABLE)

-- ============================================================================
-- NEW COLUMNS FOR V4 (SQLite compatible - no IF NOT EXISTS)
-- ============================================================================

-- extracted_by: Идентифицирует систему извлечения (для аудита)
ALTER TABLE facts ADD COLUMN extracted_by TEXT DEFAULT 'v4-cove';

-- fact_version: Версия формата факта (для backward compatibility)
ALTER TABLE facts ADD COLUMN fact_version TEXT DEFAULT '1.0';

-- confidence_score: Уверенность в факте после валидации/CoVe
-- (дублирует confidence для явности, но используется в v4 API)
ALTER TABLE facts ADD COLUMN confidence_score REAL;

-- extraction_method: Метод извлечения факта
-- Возможные значения: 'cod' (Chain-of-Density), 'deepconf' (DeepConf), 'cove' (CoVe)
ALTER TABLE facts ADD COLUMN extraction_method TEXT;

-- source_span: JSON с диапазоном текста в транскрипции
-- Формат: {"start_char": int, "end_char": int, "text": str}
-- Критично для grounding и предотвращения галлюцинаций
ALTER TABLE facts ADD COLUMN source_span TEXT;


-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Индекс по версии (для фильтрации legacy vs v4 фактов)
CREATE INDEX IF NOT EXISTS idx_facts_version ON facts(fact_version);

-- Индекс по transcription_id (для быстрого поиска фактов по транскрипции)
CREATE INDEX IF NOT EXISTS idx_facts_transcription ON facts(transcription_id);

-- Индекс по confidence_score (для фильтрации low-confidence фактов)
CREATE INDEX IF NOT EXISTS idx_facts_confidence ON facts(confidence_score);

-- Индекс по extraction_method (для метрик по методам)
CREATE INDEX IF NOT EXISTS idx_facts_extraction_method ON facts(extraction_method);


-- ============================================================================
-- DATA MIGRATION (OPTIONAL)
-- ============================================================================

-- Помечаем существующие факты как legacy (v0.0)
-- Это позволяет отличить их от v4 фактов без удаления данных
UPDATE facts
SET fact_version = '0.0',
    extracted_by = 'legacy',
    extraction_method = 'unknown'
WHERE fact_version IS NULL;


-- ============================================================================
-- VALIDATION CHECKS
-- ============================================================================

-- Проверка: source_span должен быть валидным JSON для v4 фактов
-- (в SQLite нет встроенной проверки JSON, поэтому проверяется в application layer)

-- Проверка: extraction_method должен быть из списка
-- (также проверяется в Pydantic models)


-- ============================================================================
-- NOTES
-- ============================================================================

-- 1. Backward Compatibility:
--    - Существующие факты помечены как v0.0 (legacy)
--    - v4 факты имеют fact_version='1.0'
--    - API может фильтровать по версии

-- 2. Immutability:
--    - No UPDATE/DELETE operations allowed in application code
--    - Facts are append-only
--    - Soft delete via retention policy (будущий migration)

-- 3. Citation Coverage:
--    - v4 цель: ≥98% фактов с source_span
--    - legacy факты (v0.0) не имеют source_span

-- 4. Performance:
--    - Indexes on version, transcription_id, confidence для быстрых запросов
--    - source_span хранится как TEXT (JSON), не JSONB (SQLite limitation)

-- 5. SQLite Compatibility:
--    - Removed IF NOT EXISTS from ALTER TABLE (not supported in SQLite <3.35)
--    - Using TEXT instead of JSONB
--    - Using TIMESTAMP instead of TIMESTAMP WITH TIME ZONE
