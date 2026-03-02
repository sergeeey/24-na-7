# Отчёт: Reflexio Hardening 3.3/10 → 7/10

**Дата:** 2026-03-02
**Автор:** Claude (Opus 4.6) + Сергей Кучеренко
**Период работы:** 3 сессии (Week 1-2 в одной, Week 2-3-4 в двух следующих)
**Тесты:** 585 → 588 passed, 0 failed

---

## 1. Исходная проблема

Аудит кодовой базы Reflexio 24/7 выявил критические проблемы фундамента:

| Проблема | Severity | Где |
|----------|----------|-----|
| 31 файл с прямым `sqlite3.connect()` | Critical | 16 модулей |
| Нет WAL mode | Critical | Все SQLite операции |
| Нет connection pooling | High | Каждый запрос = новое соединение |
| `INSERT OR REPLACE` уничтожает историю | High | structured_events |
| `time.sleep()` блокирует thread pool | Medium | enricher.py |
| Race conditions на lazy-init синглтонах | Medium | transcribe, diarize, filters |
| Zero-retention дыры | High | uploads/, recordings/ |
| Нет migration tracking | Medium | Все DDL "на честном слове" |

**Оценка до:** 3.3/10 (работает для 1 пользователя, рассыпается при нагрузке)

---

## 2. Что сделано (4 коммита, 30 файлов, +2129/-1285 строк)

### Week 1: SQLite WAL + Zero-Retention [`7ddf0bb`]
*5 файлов, +261/-23 строк*

**Connection Factory** (`src/storage/db.py`):
- `get_connection(db_path)` — единая точка создания SQLite connections
- 8 PRAGMA: WAL, synchronous=NORMAL, busy_timeout=5000, cache_size=64MB, mmap_size=256MB, temp_store=MEMORY, foreign_keys=ON, wal_autocheckpoint=1000
- `isolation_level=None` (autocommit mode) — предотвращает "ghost transactions" от Python sqlite3 implicit transaction management

**Zero-retention** (`src/utils/secure_delete.py`):
- `secure_delete(path)` — перезапись `os.urandom(size)` + fsync + unlink
- Замена голого `.unlink()` для аудио файлов (compliance с KZ GDPR)

**Edge cleanup** (`src/edge/listener.py`):
- Startup sweep: удаление WAV старше 1 часа
- Использование secure_delete вместо .unlink()

**Orphan sweep** (`src/api/main.py`):
- Async task `_orphan_sweep()` каждые 5 минут
- Сканирует uploads/ + recordings/, удаляет WAV старше 1 часа
- Defense in depth: если ingest крашнулся до удаления WAV

**Audio Manager** (`src/storage/audio_manager.py`):
- Context manager для `.decrypted` файлов с secure_delete в finally

---

### Week 2: DAL Consolidation [`52e616e`]
*19 файлов, +1245/-1187 строк* (самый объёмный этап)

**ReflexioDB Gateway** (`src/storage/db.py`):
- Singleton per db_path (`_instances` dict + `threading.Lock`)
- Thread-local connections через `threading.local()` — каждый поток получает свой connection
- `transaction()` context manager — explicit BEGIN + commit/rollback
- `execute()`, `fetchone()`, `fetchall()`, `executemany()`, `executescript()`
- `ensure_all_tables(db_path)` — consolidated startup с lazy imports

**Миграция 16 файлов** (по паттерну):

```
import sqlite3                          →  from src.storage.db import get_reflexio_db
conn = sqlite3.connect(str(db_path))    →  db = get_reflexio_db(db_path)
conn.row_factory = sqlite3.Row          →  (уже в get_connection)
cursor.execute(sql, params)             →  db.execute(sql, params)
cursor.fetchone()                       →  db.fetchone(sql, params)
cursor.fetchall()                       →  db.fetchall(sql, params)
conn.commit()                           →  with db.transaction(): ...
conn.close()                            →  (убрано — singleton управляет)
```

**Day 1 — Core pipeline (3 файла):**
- `src/storage/ingest_persist.py` (6 connect) — DDL без transaction(), DML в transaction()
- `src/core/audio_processing.py` (2 connect)
- `src/storage/integrity.py` (3 connect)

**Day 2 — Data modules (7 файлов):**
- `src/memory/semantic_memory.py` (4 connect)
- `src/balance/storage.py` (4 connect)
- `src/speaker/storage.py` (3 connect)
- `src/persongraph/service.py` (3 connect)
- `src/persongraph/accumulator.py` (7 methods)
- `src/persongraph/compliance.py` (4 methods)
- `src/storage/health_metrics.py` (3 connect)

**Day 3 — API + Digest (6 файлов):**
- `src/digest/generator.py` (2 connect)
- `src/digest/analyzer.py` (1 connect)
- `src/enrichment/domain_classifier.py` (1 connect)
- `src/api/routers/asr.py` (1 connect)
- `src/api/routers/metrics.py` (2 connect)
- `src/api/routers/graph.py` (1 connect)

**Conftest fixture** (`tests/conftest.py`):
- `_clean_reflexio_db_singletons` (autouse) — очищает `ReflexioDB._instances` между тестами
- Предотвращает stale connections к удалённым temp-базам

**Оставлен intentionally:**
- `src/persongraph/kuzu_engine.py` — one-shot sync из SQLite в KùzuDB, не нуждается в WAL/singleton

---

### Week 3: Thread Safety + Async Queue [`36cc57d`]
*9 файлов, +256/-80 строк*

**Step 3A: Double-check locking на lazy-init синглтонах:**

| Файл | Глобал | Lock | Почему |
|------|--------|------|--------|
| `src/asr/transcribe.py` | `_model` (WhisperModel ~600MB) | `_model_lock` | Дубль модели = 1.2GB RAM |
| `src/asr/transcribe.py` | `_asr_provider` | `_asr_lock` | YAML config read race |
| `src/asr/diarize.py` | `_pipeline` (pyannote ~600MB) | `_pipeline_lock` | Дубль pipeline = 1.2GB RAM |
| `src/core/audio_processing.py` | `_speech_filter` | `_speech_filter_lock` | FFT state corruption |

Паттерн double-check locking:
```python
if _model is not None:       # Fast path (no lock)
    return _model
with _model_lock:
    if _model is not None:   # Double check (inside lock)
        return _model
    _model = WhisperModel(...)  # Safe init
return _model
```

**Step 3B: Tenacity вместо time.sleep** (`src/enrichment/enricher.py`):
- `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))`
- Было: ручной loop + `time.sleep(2/4/8)` блокирует thread pool worker
- Стало: декларативный retry с logging hooks из коробки
- Удалены: `ENRICHMENT_MAX_RETRIES`, `ENRICHMENT_BACKOFF_SEC` константы

**Step 3C: WebSocket state encapsulation** (`src/api/routers/websocket.py`):
- Класс `_ConnectionState` вместо голого module-level dict + 3 функций
- Методы: `recent_text()`, `remember()`, `disconnect()`
- threading.Lock не нужен — asyncio single-thread event loop

**Step 3D: Async enrichment queue** (`src/enrichment/worker.py` — новый):
- `EnrichmentWorker`: asyncio.Queue (maxsize=100) + 2 worker coroutines
- `submit(task)` — fire-and-forget, QueueFull → drop with warning
- Fallback: если worker не запущен → inline `asyncio.to_thread()` (для тестов)
- Start/stop в FastAPI lifespan
- `audio_processing.py`: `await asyncio.to_thread()` → `await worker.submit()`

**Бонусный fix: integrity chain ordering:**
- `ORDER BY id ASC` → `ORDER BY ROWID ASC` в integrity.py
- UUID не гарантирует порядок вставки, ROWID — гарантирует
- Проявлялся с autocommit mode: два INSERT в одну microsecond → одинаковый created_at → сортировка по случайному UUID

---

### Week 4: Immutable Events + E2E Tests [`43596ce`]
*5 файлов, +380/-8 строк*

**Step 4A+4B: Append-only structured events** (`src/storage/ingest_persist.py`):

Было (INSERT OR REPLACE — уничтожает предыдущую версию):
```sql
INSERT OR REPLACE INTO structured_events (...) VALUES (...)
```

Стало (append-only — полная история):
```sql
-- 1. Найти текущую версию
SELECT id, version FROM structured_events
WHERE transcription_id = ? AND is_current = 1

-- 2. Пометить как superseded
UPDATE structured_events SET is_current = 0 WHERE id = ?

-- 3. Вставить новую версию
INSERT INTO structured_events (..., version, supersedes_id, is_current)
VALUES (..., old_version + 1, old_id, 1)
```

Новые колонки: `version INTEGER DEFAULT 1`, `supersedes_id TEXT`, `is_current INTEGER DEFAULT 1`
Partial index: `idx_structured_events_current ON (transcription_id) WHERE is_current = 1`
View: `current_events` — показывает только актуальные версии

**Step 4C: Migration tracking** (`src/storage/db.py`):
- Таблица `schema_migrations (name, applied_at, checksum)`
- `run_migrations(db_path)` — сканирует `migrations/sqlite/*.sql`
- Идемпотентный: пропускает уже применённые (по name)
- Первая миграция: `0010_immutable_events.sql`
- Интегрирован в lifespan после `ensure_all_tables()`

**Step 4D: E2E тесты** (`tests/e2e/test_full_pipeline.py`):

| Тест | Что проверяет |
|------|---------------|
| `test_full_ingest_pipeline` | WAV bytes → ASR → enrichment → DB → zero-retention (WAV удалён) |
| `test_reprocess_creates_new_version` | Re-enrich → version 2 (is_current=1), version 1 (is_current=0, superseded) |
| `test_migration_tracking` | Первый вызов применяет, второй — идемпотентный, schema_migrations заполнена |

---

## 3. Найденные и исправленные баги

### Баг 1: Ghost transactions (Critical)
- **Симптом:** `test_audit_ingest_endpoint_chain_valid` — chain_valid=False, проходит в изоляции
- **Причина:** Python sqlite3 `isolation_level=""` (default) магически начинает транзакции после SELECT. Singleton connections между тестами видят stale данные
- **Фикс:** `isolation_level=None` (autocommit) + explicit `BEGIN` в `transaction()`
- **Урок:** Python sqlite3 implicit transaction management — скрытый источник багов при connection reuse

### Баг 2: UUID ordering в integrity chain (Medium)
- **Симптом:** chain_valid=False когда два integrity events вставлялись в одну microsecond
- **Причина:** `ORDER BY created_at ASC, id ASC` — при одинаковом timestamp UUID `292543de...` < `e62fd19c...` (алфавитный порядок ≠ порядок вставки)
- **Фикс:** `ORDER BY created_at ASC, ROWID ASC` — ROWID монотонно возрастает
- **Урок:** Никогда не используй UUID для ordering — это random, а не sequential

### Баг 3: Unused import после рефакторинга
- **Симптом:** ruff F401 `asyncio` imported but unused
- **Причина:** `await asyncio.to_thread()` заменён на `await worker.submit()`, import остался
- **Фикс:** удалён `import asyncio`

---

## 4. Метрики

| Метрика | До | После |
|---------|-----|-------|
| Файлов с `sqlite3.connect()` | 31 | 1 (kuzu_engine, intentional) |
| WAL mode | Нет | Да, верифицируется при старте |
| Connection pooling | Нет | ReflexioDB singleton + thread-local |
| Structured events | INSERT OR REPLACE (destructive) | Append-only с version tracking |
| Thread pool blocking | time.sleep(2-8s) в enricher | tenacity + async queue |
| Race conditions | 4 unprotected singletons | 4 × threading.Lock + double-check |
| Zero-retention gaps | uploads/ не чистятся | orphan sweep каждые 5 мин + secure_delete |
| Migration tracking | Нет | schema_migrations table |
| E2E тесты | 0 (pipeline не тестировался) | 3 (ingest, reprocess, migrations) |
| Тесты всего | 585 passed | 588 passed (+3 E2E) |
| Файлов изменено | — | 30 |
| Строк кода | — | +2129 / -1285 (net +844) |

---

## 5. Архитектурные решения

### ADR-013: isolation_level=None (autocommit)
- **Контекст:** Python sqlite3 по умолчанию использует `isolation_level=""`, что магически начинает транзакции
- **Решение:** `isolation_level=None` + explicit `BEGIN` в `transaction()`
- **Обоснование:** предсказуемые границы транзакций, нет "ghost transactions"
- **Риск:** случайный DML без transaction() не будет в транзакции (autocommit каждый statement)
- **Митигация:** все DML через `with db.transaction():`

### ADR-014: Append-only вместо REPLACE
- **Контекст:** enrichment перезапускается при обновлении модели
- **Решение:** новая версия INSERT, старая помечается is_current=0
- **Обоснование:** полный аудит-трейл, возможность отката, compliance
- **Риск:** рост таблицы (N версий × M events)
- **Митигация:** partial index на is_current=1 (запросы не замедляются)

### ADR-015: Async enrichment queue вместо to_thread
- **Контекст:** 5+ concurrent WebSocket streams → LLM call 2-10s → thread pool exhaustion
- **Решение:** asyncio.Queue + 2 workers, submit() fire-and-forget
- **Обоснование:** ограничение concurrent LLM calls, caller не блокируется
- **Fallback:** inline execution через to_thread если queue не запущена (тесты)

---

## 6. Что осталось за рамками

| Пункт | Статус | Почему не сейчас |
|-------|--------|-----------------|
| Supabase миграция | Backlog | MVP на SQLite, Supabase — при >100 users |
| Redis rate limiting | Backlog | slowapi memory backend достаточен для 3-10 users |
| Async PostgreSQL | Backlog | SQLite + WAL хватает для single-server |
| Connection pool limit | Monitoring | thread-local = 1 conn per thread, достаточно |
| Structured events pruning | Backlog | Таблица растёт медленно при 3-10 users |

---

## 7. Рекомендации на будущее

1. **Мониторинг WAL size:** `PRAGMA wal_checkpoint(TRUNCATE)` периодически, если WAL растёт >100MB
2. **Structured events pruning:** если >10K versions — добавить cleanup старых (is_current=0) старше 90 дней
3. **Connection pool metrics:** добавить structlog счётчик active connections per thread
4. **Load test:** wrk/locust на `/ws/ingest` с 10 concurrent streams — проверить thread pool + queue behavior
