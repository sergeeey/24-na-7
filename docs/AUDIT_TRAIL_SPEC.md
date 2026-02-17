# Audit Trail Specification для Reflexio 24/7

**Версия:** v4.1.1 Enhanced
**Дата:** 2026-02-17
**Назначение:** Production-grade audit trail для compliance, troubleshooting, и performance analysis

---

## Обзор

Enhanced audit trail для retention operations с полным контекстом выполнения, производительности и безопасности.

### Ключевые улучшения (v4.1.1)

1. **Execution Context** — job_run_id связывает все операции одного запуска
2. **Environment Context** — окружение, host, версии для воспроизводимости
3. **Performance Metrics** — duration_ms, rows_scanned для диагностики
4. **Security/Scale** — min/max_deleted_id для больших datasets, JSON-структуры

---

## Schema (v4.1.1)

```sql
CREATE TABLE retention_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Основная информация
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL,                -- DELETE|SOFT_DELETE|ARCHIVE|PURGE
    record_count INTEGER NOT NULL,
    deleted_ids TEXT,                       -- JSON array, limit 1000
    retention_rule TEXT,                    -- JSON object
    cutoff_date TIMESTAMP,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dry_run BOOLEAN DEFAULT 0,
    error_message TEXT,

    -- Execution context (v4.1.1)
    job_run_id TEXT,                        -- UUID, связывает операции одного запуска
    job_name TEXT DEFAULT 'retention_cleanup',
    trigger TEXT DEFAULT 'cron',            -- cron|manual|ci|api
    actor TEXT DEFAULT 'system',            -- system|username|service_account

    -- Environment context
    environment TEXT,                       -- dev|staging|prod
    host TEXT,
    app_version TEXT,
    db_schema_version TEXT,

    -- Performance/scale
    duration_ms INTEGER,
    rows_scanned INTEGER,                   -- Сколько проверили (vs record_count = сколько удалили)
    min_deleted_id INTEGER,
    max_deleted_id INTEGER
);

-- Индексы для compliance/troubleshooting
CREATE INDEX idx_audit_job_run_id ON retention_audit_log(job_run_id);
CREATE INDEX idx_audit_environment ON retention_audit_log(environment);
CREATE INDEX idx_audit_trigger ON retention_audit_log(trigger);
CREATE INDEX idx_audit_table_executed ON retention_audit_log(table_name, executed_at);
CREATE INDEX idx_audit_error ON retention_audit_log(error_message) WHERE error_message IS NOT NULL;
```

---

## Поля (детали)

### Основная информация

| Поле | Тип | Описание | Пример |
|------|-----|----------|--------|
| **table_name** | TEXT | Имя таблицы | `"transcriptions"` |
| **operation** | TEXT | Тип операции (enum) | `"DELETE"` |
| **record_count** | INTEGER | Количество удалённых записей | `42` |
| **deleted_ids** | TEXT (JSON) | Массив ID (limit 1000) | `"[1, 2, 3]"` |
| **retention_rule** | TEXT (JSON) | Правило retention | `{"table":"transcriptions","retention_days":90}` |
| **cutoff_date** | TIMESTAMP | Граница удаления (старше → под удаление) | `"2025-11-19 00:00:00"` |
| **executed_at** | TIMESTAMP | Время выполнения (UTC) | `"2026-02-17 23:15:30"` |
| **dry_run** | BOOLEAN | Dry run mode (0/1) | `0` |
| **error_message** | TEXT | Сообщение об ошибке (если есть) | `"Table does not exist"` или `NULL` |

### Execution Context (v4.1.1)

| Поле | Тип | Описание | Пример |
|------|-----|----------|--------|
| **job_run_id** | TEXT (UUID) | Уникальный ID запуска, связывает все операции | `"c2b6f1a0-..."` |
| **job_name** | TEXT | Имя job | `"retention_cleanup"` |
| **trigger** | TEXT | Источник запуска | `"cron"` / `"manual"` / `"ci"` / `"api"` |
| **actor** | TEXT | Кто/что запустило | `"system"` / `"username"` / `"service_account"` |

### Environment Context

| Поле | Тип | Описание | Пример |
|------|-----|----------|--------|
| **environment** | TEXT | Окружение | `"prod"` / `"staging"` / `"dev"` |
| **host** | TEXT | Hostname сервера | `"reflexio-prod-01"` |
| **app_version** | TEXT | Версия приложения | `"v4.1.1"` |
| **db_schema_version** | TEXT | Версия схемы БД | `"0004"` |

### Performance/Scale

| Поле | Тип | Описание | Пример |
|------|-----|----------|--------|
| **duration_ms** | INTEGER | Время выполнения (миллисекунды) | `234` |
| **rows_scanned** | INTEGER | Количество проверенных записей | `150` (vs record_count=42 удалённых) |
| **min_deleted_id** | INTEGER | Минимальный ID удалённых записей | `1001` |
| **max_deleted_id** | INTEGER | Максимальный ID удалённых записей | `1042` |

---

## Use Cases

### 1. Compliance Audit

**Вопрос:** "Какие данные были удалены в production за последние 30 дней?"

```sql
SELECT
    table_name,
    SUM(record_count) as total_deleted,
    COUNT(*) as operations_count
FROM retention_audit_log
WHERE
    environment = 'prod'
    AND executed_at >= datetime('now', '-30 days')
    AND dry_run = 0
    AND error_message IS NULL
GROUP BY table_name;
```

**Результат:**
```
table_name       | total_deleted | operations_count
-----------------|---------------|------------------
transcriptions   | 1,245         | 30
facts            | 523           | 30
digests          | 89            | 30
```

### 2. Troubleshooting Failed Job

**Вопрос:** "Почему retention job упал сегодня утром?"

```sql
SELECT
    job_run_id,
    table_name,
    error_message,
    duration_ms,
    executed_at
FROM retention_audit_log
WHERE
    executed_at >= datetime('now', '-1 day')
    AND error_message IS NOT NULL
ORDER BY executed_at DESC;
```

**Результат:**
```
job_run_id         | table_name | error_message         | duration_ms | executed_at
-------------------|------------|-----------------------|-------------|------------------
c2b6f1a0-...       | facts      | Table does not exist  | 12          | 2026-02-17 08:15:30
```

### 3. Performance Analysis

**Вопрос:** "Какие таблицы slow для retention cleanup?"

```sql
SELECT
    table_name,
    AVG(duration_ms) as avg_duration,
    AVG(rows_scanned) as avg_scanned,
    AVG(record_count) as avg_deleted
FROM retention_audit_log
WHERE
    error_message IS NULL
    AND dry_run = 0
    AND executed_at >= datetime('now', '-7 days')
GROUP BY table_name
ORDER BY avg_duration DESC;
```

**Результат:**
```
table_name       | avg_duration | avg_scanned | avg_deleted
-----------------|--------------|-------------|-------------
transcriptions   | 234          | 150         | 42
facts            | 89           | 30          | 15
digests          | 23           | 5           | 3
```

### 4. Job Run Investigation

**Вопрос:** "Что именно делал job run `c2b6f1a0-...`?"

```sql
SELECT
    table_name,
    operation,
    record_count,
    duration_ms,
    dry_run,
    error_message
FROM retention_audit_log
WHERE job_run_id = 'c2b6f1a0-...'
ORDER BY executed_at;
```

**Результат:** Все операции этого запуска с полным контекстом.

### 5. Security/PII Analysis

**Вопрос:** "Какие ID были удалены из production в феврале?"

```sql
SELECT
    executed_at,
    table_name,
    min_deleted_id,
    max_deleted_id,
    record_count
FROM retention_audit_log
WHERE
    environment = 'prod'
    AND strftime('%Y-%m', executed_at) = '2026-02'
    AND dry_run = 0
ORDER BY executed_at;
```

**Альтернатива:** Если нужны полные ID (не PII):
```sql
SELECT
    executed_at,
    table_name,
    deleted_ids  -- JSON array (limit 1000)
FROM retention_audit_log
WHERE environment = 'dev';  -- Только для dev/staging
```

---

## API Usage

### Инициализация с контекстом

```python
from src.storage.retention import RetentionPolicy

# Production cron job
policy = RetentionPolicy(
    db_path="src/storage/reflexio.db",
    job_name="retention_cleanup",
    trigger="cron",
    actor="system",
    environment="prod"
)

# Manual cleanup by admin
policy = RetentionPolicy(
    db_path="src/storage/reflexio.db",
    job_name="manual_cleanup",
    trigger="manual",
    actor="admin@example.com",
    environment="prod"
)

# CI/CD cleanup
policy = RetentionPolicy(
    db_path="src/storage/reflexio.db",
    job_name="ci_cleanup",
    trigger="ci",
    actor="github-actions",
    environment="staging"
)
```

### Cleanup с audit trail

```python
# Dry run (не удаляет, только логирует)
results = policy.cleanup_expired_data(dry_run=True)
# results: {"transcriptions": 42, "facts": 15, "digests": 3}

# Actual cleanup
results = policy.cleanup_expired_data(dry_run=False)
```

### Query audit log

```python
# Все logs
logs = policy.get_audit_log(limit=100)

# Logs для конкретной таблицы
logs = policy.get_audit_log(table_filter="transcriptions", limit=50)

# Logs с определённой даты
from datetime import datetime, timedelta
since = datetime.now() - timedelta(days=7)
logs = policy.get_audit_log(since=since)

# Пример результата
for log in logs:
    print(f"{log['executed_at']}: {log['table_name']} — {log['record_count']} records")
    print(f"  Job: {log['job_name']} (trigger={log['trigger']}, actor={log['actor']})")
    print(f"  Performance: {log['duration_ms']}ms, scanned {log['rows_scanned']} rows")
```

---

## Migration от v4.1 к v4.1.1

### Применение migration

```bash
# Apply migration
sqlite3 src/storage/reflexio.db < src/storage/migrations/0004_audit_log_enhancements.sql
```

### Backward Compatibility

**Старые записи (v4.1):** Новые поля будут `NULL` для старых записей.

**Новые записи (v4.1.1):** Все поля заполнены.

**Query compatibility:** Все старые запросы работают (новые поля опциональны).

---

## Best Practices

### 1. Разделение окружений

```python
# Environment из переменной окружения
import os
environment = os.getenv("ENVIRONMENT", "dev")

policy = RetentionPolicy(
    db_path="src/storage/reflexio.db",
    environment=environment
)
```

### 2. PII Protection

**В production:**
- Логируем min/max_deleted_id (диапазон)
- deleted_ids ограничен до 1000 (не логируем весь dataset)
- Не логируем содержимое удалённых записей

**В dev/staging:**
- Можно логировать полные deleted_ids для debugging

### 3. Performance Monitoring

```sql
-- Alert если cleanup слишком долгий
SELECT * FROM retention_audit_log
WHERE duration_ms > 5000  -- >5s
AND executed_at >= datetime('now', '-1 day');
```

### 4. Error Alerting

```sql
-- Alert на ошибки retention
SELECT * FROM retention_audit_log
WHERE error_message IS NOT NULL
AND executed_at >= datetime('now', '-1 hour');
```

---

## Testing

### Unit Tests

**22 теста проходят (10 v4.1 + 12 v4.1.1):**
- `tests/test_retention_audit.py` — базовые audit tests
- `tests/test_retention_audit_enhanced.py` — enhanced fields tests

### Coverage

```bash
pytest tests/test_retention_audit*.py --cov=src.storage.retention
# Coverage: ≥90% для retention.py
```

---

## Appendix: JSON Formats

### retention_rule (пример)

```json
{
  "table": "transcriptions",
  "retention_days": 90,
  "timestamp_column": "created_at",
  "soft_delete": false,
  "delete_column": null
}
```

### deleted_ids (пример)

```json
[1, 2, 3, 42, 100, 150]
```

**Limit:** Первые 1000 IDs (для больших datasets используем min/max_deleted_id).

---

**Статус:** ✅ Production-Ready (v4.1.1)
**Migration:** 0004_audit_log_enhancements.sql
**Tests:** 22/22 passing
