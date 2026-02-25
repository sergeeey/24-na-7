# Техническое задание: Reflexio 24/7
**Версия:** 2.0 | **Дата:** 2026-02-25 | **Статус:** Рабочий документ

---

## 1. МИССИЯ И ЦЕЛЬ ПРОДУКТА

**Reflexio 24/7** — AI-нативный персональный помощник, который работает в фоне 24 часа в сутки, слушает только голос пользователя, транскрибирует, анализирует и к вечеру предоставляет объективное зеркало дня.

### Три уровня зрелости продукта

| Уровень | Название | Готовность | Описание |
|---------|----------|-----------|----------|
| L1 | Фиксация | ~85% | Запись → транскрипция → хранение → дайджест |
| L2 | Понимание | ~20% | Паттерны, эмоции, темы, задачи, колесо баланса |
| L3 | Когнитивный двойник | ~0% | PersonGraph, предсказание поведения, рекомендации |

**Цель настоящего ТЗ:** довести L1 до 100%, реализовать L2 полностью, заложить фундамент L3.

### North Star метрика
> "Пользователь читает вечерний дайджест и узнаёт о себе что-то важное, чего сам не замечал."

---

## 2. ТЕКУЩАЯ АРХИТЕКТУРА (AS-IS)

### 2.1 Полный Pipeline

```
[Pixel 9 Pro]
  AudioRecord (16kHz, PCM16, mono)
  → webrtcvad (aggressiveness=2, 30ms frames, 2-сек тишина = конец сегмента)
  → VadSegmentWriter → WAV файл (filesDir/audio_records/)
  → IngestWebSocketClient (ws://host:8000/ws/ingest, Binary frame)

[Сервер: reflexio-api Docker]
  WebSocket handler (websocket.py)
  → P0: SpeechFilter (FFT: speech 300-3400Hz vs music >4kHz, FILTER_MUSIC=true)
  → Whisper medium (language=ru, CPU, int8)
  → P1: _is_meaningful_transcription (min 3 слова, не стоп-фразы, lang_prob>0.4)
  → Privacy pipeline (PRIVACY_MODE=audit, PII detection)
  → persist_ws_transcription() → SQLite: ingest_queue + transcriptions
  → append_integrity_event() → SQLite: integrity_events (SHA-256 chain)
  → WAV удалён на сервере (P2)
  → JSON → Android: {"type":"transcription","text":"...","file_id":"..."}
  → Android: WAV удалён на телефоне (P3), enrichment запрошен через 3+5 сек

  [Async] _enrich_and_persist():
    → enrich_transcription() → analyze_recording_text() → LLM (gpt-4o-mini)
    → persist_structured_event() → SQLite: structured_events
    → consolidate_to_memory_node() → SQLite: memory_nodes

[Telegram Bot]
  22:50 → /digest (daily digest generation)
  23:10 → checkin (вопрос о дне)
```

### 2.2 Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Backend | Python 3.11, FastAPI, uvicorn |
| ASR | faster-whisper (medium, CPU, int8) |
| LLM | gpt-4o-mini (actor+critic), claude-haiku (enrichment) |
| DB (dev) | SQLite (D:/24 na 7/src/storage/recordings.db) |
| DB (prod) | Supabase (PostgreSQL) |
| Bot | Telegram (aiogram) |
| Android | Kotlin, Jetpack Compose, OkHttp WebSocket, Room |
| Устройство | Pixel 9 Pro |
| GPU | NVIDIA RTX 5070 Ti (16GB VRAM) — НЕ ИСПОЛЬЗУЕТСЯ для ASR |
| Deploy | Docker, docker-compose |
| Auth | Bearer token (API_KEY env), WebSocket header |
| Privacy | PII detection (PIIDetector), SHA-256 integrity chain |

### 2.3 Схема базы данных (SQLite)

```sql
-- Очередь входящих файлов
ingest_queue (
    id TEXT PK,           -- file_id (UUID, генерируется Android)
    filename TEXT,
    file_path TEXT,
    file_size INTEGER,
    status TEXT,          -- 'pending' | 'processed'
    created_at TEXT,
    processed_at TEXT,
    error_message TEXT
)

-- Сырые транскрипции от Whisper
transcriptions (
    id TEXT PK,
    ingest_id TEXT → ingest_queue.id,
    text TEXT,
    language TEXT,
    language_probability REAL,
    duration REAL,
    segments TEXT,        -- JSON [{text,start,end,confidence}]
    created_at TEXT
)

-- Структурированные события после LLM enrichment
structured_events (
    id TEXT PK,
    transcription_id TEXT → transcriptions.id,
    timestamp TEXT,
    duration_sec REAL,
    text TEXT,
    language TEXT,
    summary TEXT,
    emotions TEXT,        -- JSON ["радость","тревога"]
    topics TEXT,          -- JSON ["работа","встреча"]
    tasks TEXT,           -- JSON [{text,priority,deadline}]
    decisions TEXT,       -- JSON ["решение 1"]
    speakers TEXT,        -- JSON [] (всегда пусто, будущее)
    urgency TEXT,         -- low|medium|high
    sentiment TEXT,       -- positive|neutral|negative
    location TEXT,        -- NULL (всегда)
    asr_confidence REAL,
    enrichment_confidence REAL,
    enrichment_model TEXT,
    enrichment_tokens INTEGER,
    enrichment_latency_ms REAL,
    created_at TEXT
)

-- Legacy анализы (старый путь)
recording_analyses (
    id TEXT PK,
    transcription_id TEXT,
    summary TEXT,
    emotions TEXT,        -- JSON
    actions TEXT,         -- JSON
    topics TEXT,          -- JSON
    urgency TEXT,
    created_at TEXT
)

-- Semantic memory nodes
memory_nodes (
    id TEXT PK,
    source_ingest_id TEXT,
    source_transcription_id TEXT,
    content TEXT,
    summary TEXT,
    topics_json TEXT,
    entities_json TEXT,
    created_at TEXT
)

-- Retrieval traces
retrieval_traces (
    id TEXT PK,
    query TEXT,
    node_ids_json TEXT,
    top_k INTEGER,
    created_at TEXT
)

-- Integrity hash chain
integrity_events (
    id TEXT PK,
    ingest_id TEXT,
    stage TEXT,           -- 'ingest_received' | 'transcription_complete' | ...
    content_hash TEXT,    -- SHA-256
    prev_hash TEXT,       -- ссылка на предыдущий
    metadata TEXT,        -- JSON
    created_at TEXT
)
```

### 2.4 REST API (FastAPI)

| Метод | URL | Описание |
|-------|-----|----------|
| GET | / | Health + feature flags |
| GET | /health | Health check |
| WS | /ws/ingest | WebSocket: binary WAV → transcription |
| POST | /ingest/audio | REST: multipart WAV upload |
| GET | /digest/daily?date=YYYY-MM-DD | Дайджест дня (JSON) |
| GET | /digest/today | Дайджест сегодня |
| GET | /digest/{date} | Дайджест по дате |
| GET | /digest/{date}/density | Информационная плотность |
| GET | /asr/models | Список моделей ASR |
| POST | /asr/transcribe | Транскрибировать файл |
| GET | /memory/search?q=... | Поиск в semantic memory |
| GET | /audit/trail/{ingest_id} | Integrity chain отчёт |
| GET | /search/transcriptions | Поиск транскрипций |
| GET | /metrics | Метрики (EXTENDED_METRICS=false → только базовые) |
| GET | /enrichment/{file_id} | Enrichment данные по file_id |

### 2.5 Android (Pixel 9 Pro)

**Компоненты:**
- `AudioRecordingService` — foreground service, `START_STICKY`, запись 24/7
- `VadSegmentWriter` — webrtcvad, 30ms frames, буферизация → WAV
- `IngestWebSocketClient` — OkHttp WebSocket, binary WAV, получает JSON
- `EnrichmentApiClient` — HTTP GET /enrichment/{file_id}, 2 попытки (3с + 5с)
- `RecordingDao` / `RecordingDatabase` — Room, локальное хранилище метаданных
- `MainActivity` + Compose UI — список записей, аналитика, дайджест

**Протокол WebSocket:**
```
Android → Server: [WAV bytes binary]
Server → Android: {"type":"received","file_id":"uuid"}
Server → Android: {"type":"transcription","text":"текст","file_id":"uuid"}
    ИЛИ: {"type":"filtered","file_id":"uuid"}  (шум/музыка)
    ИЛИ: {"type":"error","message":"..."}
```

---

## 3. ТЕКУЩИЕ БАГИ И ПРОБЕЛЫ

### 🔴 Критические (блокируют работу)

#### BUG-001: MAX_TEXT_LENGTH_FOR_LLM = 4000 — Root Cause сломанного CoD
**Файл:** `src/digest/generator.py`
**Проблема:** Длинные встречи (>15 минут) обрезаются до 4000 символов.
Chain of Density получает неполный контекст → пустые или бессмысленные summary.
**Решение:** Поднять до 16000 (Claude Haiku контекст 200K), добавить tiered chunking:
- Сначала summarize каждые N записей отдельно
- Потом summary-of-summaries

#### BUG-002: Казахский язык молча ломается
**Файл:** `src/utils/config.py`, `src/asr/transcribe.py`
**Проблема:** `ASR_LANGUAGE=ru` принудительно, Whisper транскрибирует казахский как "русский" — текст коверкается, confidence 1.0 (ложно-высокое).
**Решение:** auto-detect (lang=None) + post-check: если detected_lang в ["kk","ru"] — accept, иначе discard.

#### BUG-003: Две несинхронизированные pipeline
**Файлы:** `websocket.py` + `src/api/routers/ingest.py`
**Проблема:** REST POST /ingest/audio и WebSocket имеют разный код обработки. Фиксы применяются только к WebSocket. REST путь содержит устаревшие баги.
**Решение:** Вынести общую логику в `src/core/audio_processing.py`, оба роутера используют один модуль.

#### BUG-004: GPU не используется для ASR
**Конфиг:** `ASR_DEVICE=cpu`, RTX 5070 Ti доступна
**Влияние:** Whisper medium на CPU ≈ 5-10× реального времени. При частых коротких сегментах → очередь.
**Решение:** `ASR_DEVICE=cuda`, `ASR_COMPUTE_TYPE=float16` в Docker (при наличии GPU passthrough).

#### BUG-005: CoreMemory хранится в `.cursor/` папке
**Файл:** `D:/24 na 7/.cursor/memory/core_memory.json`
**Проблема:** Удаление Cursor IDE = потеря core memory. Не в git-tracked path.
**Решение:** Перенести в `D:/24 na 7/src/storage/core_memory.json`.

### 🟡 Важные (деградируют качество)

#### BUG-006: Стоп-фразы только на английском
**Файл:** `websocket.py`, `enricher.py`
`_NOISE_PHRASES` и `WHISPER_HALLUCINATIONS` не включают русские шумы:
`"угу"`, `"ага"`, `"ну"`, `"мм"`, `"это"`, `"так"`, `"ладно"`
→ Мусор попадает в БД и портит дайджест.

#### BUG-007: 2-секундный silence VAD разрывает семантику
**Файл:** `android/.../VadSegmentWriter.kt`
**Проблема:** "Я думаю... [2.1 сек пауза] ...что нужно сделать завтра" → два отдельных сегмента. Enrichment теряет связь между мыслями.
**Решение:** Extend silence до 3-4 секунд + merge-близкие-сегменты на сервере (если два сегмента < 5 сек друг от друга → join).

#### BUG-008: enrichment_confidence всегда 0.8
**Файл:** `src/enrichment/enricher.py` строка 117
`base_event.enrichment_confidence = 0.8` — hardcoded. Нет реальной оценки.
**Решение:** confidence = f(summary length, topics count, sentiment≠neutral).

#### BUG-009: Async enrichment без retry
**Файл:** `websocket.py` — `_enrich_and_persist()`
Если LLM вернул ошибку (таймаут, rate limit) — enrichment не повторяется.
Транскрипция остаётся без summary/topics.
**Решение:** Добавить retry с exponential backoff (3 попытки, 2/4/8 секунд).

#### BUG-010: SAFE checker warning при каждом запросе
**Файл:** `src/api/main.py` (middleware)
Нет `src/validation/` модуля → импорт падает с warning каждый запрос.
**Решение:** Создать `src/validation/safe_checker.py` или убрать warning.

#### BUG-011: DigestGenerator берёт ПОСЛЕДНИЕ N записей, не ВСЕ
**Файл:** `src/digest/generator.py`
`MAX_TRANSCRIPTIONS_FOR_LLM=100` берёт последние 100. Если за день 150 записей — первая треть дня игнорируется.
**Решение:** Tiered approach: сначала summarize каждый час отдельно, потом дневной дайджест из часовых summary.

#### BUG-012: topics[] смешивает темы и домены
**Текущее:** `topics = ["работа", "встреча", "здоровье", "бег", "семья"]`
**Проблема:** Невозможно отфильтровать "все записи про здоровье" vs "все встречи про работу".
**Решение:** Разделить на `topics[]` (конкретные: "встреча с Иваном") и `domains[]` (8 доменов: work/health/family/finance/psychology/relations/growth/leisure).

#### BUG-013: Semantic memory — только LIKE-поиск
**Файл:** `src/memory/semantic_memory.py`
`retrieve_memory()` использует `WHERE lower(content) LIKE ?` — нет смысловых совпадений.
**Решение:** Stage-2 память: text-embedding-3-small (1536 dim) → pgvector в Supabase.

#### BUG-014: Android enrichment fetch — только 2 попытки
**Файл:** `AudioRecordingService.kt`
Если сервер перегружен → enrichment не придёт на Android.
**Решение:** Добавить background sync job (WorkManager) каждые 30 минут.

#### BUG-015: Нет offline queue на Android
**Проблема:** Если Wi-Fi нет → сегменты теряются (WAV записан, upload failed, retry нет).
**Решение:** Room queue + WorkManager для retry when network available.

### 🟢 Технический долг

- 54 `.md` файла в корне репозитория (мусор)
- `android/.gradle/` не в `.gitignore`
- `config/asr.yaml` `local.device: cuda` противоречит `Settings.ASR_DEVICE=cpu`
- `config/asr.yaml` `model: whisper-v3-turbo` игнорируется (settings берёт `ASR_MODEL_SIZE`)
- Нет метрик таблицы (создан endpoint `/metrics` но нет CREATE TABLE)
- Supabase RLS не настроен (READ/WRITE открыты)
- `src:/app/src` volume mount в Docker — нельзя использовать в production
- Нет rate limiting в WebSocket (только REST)
- Нет circuit breaker для LLM вызовов

---

## 4. ПЛАН РЕАЛИЗАЦИИ (ПРИОРИТЕТЫ)

### 4.1 Спринт 1: Стабилизация Core (1-2 недели)

#### Задача 1.1: Fix CoD — поднять MAX_TEXT_LENGTH_FOR_LLM
```python
# Текущее: MAX_TEXT_LENGTH_FOR_LLM = 4000
# Нужно: tiered chunking
# 1) Группировать transcriptions по часам
# 2) Summarize каждый час (LLM #1)
# 3) Daily digest из hourly summaries (LLM #2)
```
**Файл:** `src/digest/generator.py`
**Результат:** CoD работает для любой длины дня.

#### Задача 1.2: Русские стоп-фразы
```python
# Добавить в _NOISE_PHRASES:
RU_NOISE = {"угу", "ага", "ну", "мм", "хм", "это", "ладно", "понял", "окей"}
# Добавить в WHISPER_HALLUCINATIONS:
RU_HALLUCINATIONS = {"спасибо.", "спасибо за просмотр.", "подписывайтесь."}
```
**Файлы:** `websocket.py`, `enricher.py`

#### Задача 1.3: Разделить topics[] и domains[]
```sql
-- Добавить колонку domains TEXT DEFAULT '[]' в structured_events
-- Заполнять через DomainClassifier (см. раздел 5)
```

#### Задача 1.4: Перенести CoreMemory
```bash
mv .cursor/memory/core_memory.json src/storage/core_memory.json
# Обновить все импорты
```

#### Задача 1.5: Создать src/validation/safe_checker.py
Убрать warning при каждом запросе.

#### Задача 1.6: Unified audio processing pipeline
Вынести общую логику WebSocket + REST в `src/core/audio_processing.py`.

### 4.2 Спринт 2: Качество анализа (2-4 недели)

#### Задача 2.1: Реальный enrichment_confidence
```python
def compute_enrichment_confidence(analysis: dict) -> float:
    score = 0.0
    if len(analysis.get("summary", "")) > 30: score += 0.3
    if len(analysis.get("topics", [])) >= 2: score += 0.2
    if len(analysis.get("emotions", [])) >= 1: score += 0.2
    if analysis.get("urgency") != "medium": score += 0.15
    if len(analysis.get("actions", [])) >= 1: score += 0.15
    return round(min(score, 1.0), 2)
```

#### Задача 2.2: Retry для async enrichment
```python
async def _enrich_and_persist(ingest_id, text, ...):
    for attempt in range(3):
        try:
            result = await enrich_transcription(...)
            break
        except Exception:
            await asyncio.sleep(2 ** attempt)
```

#### Задача 2.3: Segment merging на сервере
Если два сегмента пришли < 5 секунд друг за другом от одного WS соединения → объединять перед enrichment.

#### Задача 2.4: ASR language auto-detect + validation
```python
# Не ASR_LANGUAGE=ru принудительно, а:
segments, info = model.transcribe(audio, language=None)
if info.language not in ["ru", "kk", "en"]:
    return None  # Reject
```

#### Задача 2.5: Android offline queue (WorkManager)
```kotlin
// RecordingUploadWorker extends CoroutineWorker
// Constraints: NetworkType.CONNECTED
// Input: recordingId
// Retry policy: exponential, max 3 attempts
```

### 4.3 Спринт 3: Колесо Баланса (1 месяц)

Полная реализация описана в **разделе 5**.

### 4.4 Спринт 4: Stage-2 Память (2 месяца)

Векторные эмбеддинги + PersonGraph — описан в **разделе 6**.

---

## 5. КОЛЕСО БАЛАНСА

### 5.1 Концепция

Wheel of Balance (ВоБ) — автоматическая классификация каждой транскрипции по жизненным доменам для отслеживания баланса жизни пользователя.

**Ключевой принцип:** домены универсальные → персональные ключевые слова.
Система знает базовые 8 доменов, но пользователь может добавить свои.

### 5.2 Домены по умолчанию (для Сергея)

| Домен | Ключевые слова (примеры) | Иконка |
|-------|------------------------|--------|
| `work` | работа, задача, встреча, проект, клиент, дедлайн, банк, безопасность | 💼 |
| `health` | здоровье, бег, тренировка, еда, сон, врач, усталость, болит | 🏃 |
| `family` | жена, дети, мама, папа, дом, ужин, выходные, Алматы | 👨‍👩‍👦 |
| `finance` | деньги, зарплата, расходы, кредит, инвестиции, тенге | 💰 |
| `psychology` | чувствую, тревога, стресс, радость, злость, думаю, осознал | 🧠 |
| `relations` | друзья, коллеги, конфликт, поддержка, общение, доверие | 🤝 |
| `growth` | учусь, книга, курс, идея, цель, развитие, навык | 🌱 |
| `leisure` | отдых, кино, игра, прогулка, хобби, путешествие, музыка | 🎯 |

### 5.3 Архитектура DomainClassifier

```python
# src/balance/domain_classifier.py

class DomainClassifier:
    """Классифицирует текст по доменам колеса баланса."""

    def classify(self, text: str, topics: list[str]) -> list[str]:
        """
        Returns: список доменов ['work', 'health']

        Логика (в порядке приоритета):
        1. Exact match: topics[] содержит домен-ключевое слово
        2. Keyword match: text содержит ключевые слова домена
        3. LLM fallback: если confidence < 0.6, отправить в LLM
        """
        ...
```

```sql
-- Добавить в structured_events:
ALTER TABLE structured_events ADD COLUMN domains TEXT DEFAULT '[]';

-- Новая таблица: настройки доменов
CREATE TABLE domain_config (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,        -- 'work', 'health', 'custom_domain'
    display_name TEXT NOT NULL,  -- 'Работа', 'Здоровье', 'Мой бизнес'
    keywords_json TEXT,          -- JSON ["слово1", "слово2"]
    color TEXT DEFAULT '#6366f1',
    icon TEXT DEFAULT '📌',
    is_active BOOLEAN DEFAULT true,
    created_at TEXT
);

-- Агрегация по доменам для колеса
CREATE VIEW domain_balance AS
SELECT
    date(created_at) as day,
    domain,
    COUNT(*) as mention_count,
    AVG(CASE WHEN sentiment='positive' THEN 1
             WHEN sentiment='negative' THEN -1
             ELSE 0 END) as avg_sentiment
FROM structured_events, json_each(domains)
GROUP BY day, domain;
```

### 5.4 API для колеса баланса

```
GET /balance/wheel?date=YYYY-MM-DD
GET /balance/wheel?from=YYYY-MM-DD&to=YYYY-MM-DD
GET /balance/domains                    -- список доменов пользователя
POST /balance/domains                   -- добавить кастомный домен
PUT /balance/domains/{domain}           -- изменить ключевые слова
GET /balance/insights                   -- AI-анализ дисбаланса
```

**Ответ GET /balance/wheel:**
```json
{
  "date": "2026-02-25",
  "domains": [
    {"domain": "work", "score": 8.2, "mentions": 47, "sentiment": -0.2},
    {"domain": "health", "score": 1.1, "mentions": 3, "sentiment": 0.1},
    {"domain": "family", "score": 2.3, "mentions": 8, "sentiment": 0.5}
  ],
  "balance_score": 0.34,
  "alert": "Сегодня работа занимает 78% дня. Последний раз о здоровье — 3 дня назад.",
  "recommendation": "Завтра запланируй 30 минут для себя."
}
```

### 5.5 Интеграция в дайджест

```markdown
## Колесо Баланса — 25 февраля

💼 Работа       ████████████ 8.2/10 (48 упоминаний)
🧠 Психология   ████         3.1/10 (12 упоминаний)
👨‍👩‍👦 Семья        ███          2.3/10 (8 упоминаний)
🏃 Здоровье     █            1.1/10 (3 упоминания)

⚠️ Дисбаланс: Здоровье — 4 дня игнорируется
```

---

## 6. ПЕРСОНАЛЬНЫЙ ГРАФ (PERSONALGRAPH) — ПЛАН L3

### 6.1 Концепция

PersonGraph — динамическая модель пользователя: кто он, как думает, что его беспокоит, как меняется со временем.

**Входные данные:**
- Транскрипции (ежедневные)
- Паттерны из колеса баланса
- Эмоциональные тренды
- Задачи (выполнены/нет)

### 6.2 Психологические маркеры (LIWC-подобные)

| Маркер | Сигналы | Интерпретация |
|--------|---------|---------------|
| Тревожность | слова "всегда", "никогда", "невозможно", "страшно" | Катастрофизация |
| Самокритика | "я плохо", "опять я", "снова не смог" | Внутренний критик |
| Перфекционизм | "надо лучше", "недостаточно", "не готово" | Blockers для действий |
| Прокрастинация | "потом", "завтра", "ещё не" + deadline пропущен | Паттерн откладывания |
| Энергия | темп речи, длина сегментов, интенсивность | Эмоциональный заряд |
| Социальная изоляция | ≤2 упоминания людей за неделю | Риск изоляции |

```python
# src/psychology/liwc_markers.py

ABSOLUTIST_WORDS = {"всегда", "никогда", "невозможно", "обязан", "должен"}
SELF_CRITICAL = {"опять я", "снова не", "как всегда плохо"}
PROCRASTINATION = {"потом", "завтра", "как-нибудь", "ещё успею"}

def analyze_linguistic_markers(text: str) -> dict:
    return {
        "absolutism_score": count_matches(text, ABSOLUTIST_WORDS) / word_count(text),
        "self_criticism_score": ...,
        "procrastination_signals": ...,
    }
```

### 6.3 Temporal Knowledge Graph (Graphiti/Zep интеграция)

```python
# Узлы GraphPersonal:
# Person (Сергей)
# → HAS_DOMAIN → DomainBalance (work, health...)
# → EXPERIENCED_EMOTION → EmotionEvent (тревога, 2026-02-25)
# → MENTIONED_TASK → Task (uuid, created, completed?)
# → HAS_PATTERN → BehaviorPattern (procrastination, прокрастинация по пятницам)
# → KNOWS_PERSON → Contact (коллега, жена...)

# Edges имеют timestamp → можно видеть как граф эволюционирует
```

**Стек:** Graphiti (Python) + Supabase pgvector.

### 6.4 "100 мудрецов" — Архитектура анализа

Вместо одного промпта — ансамбль из 5 специализированных аналитиков:

```python
ANALYSTS = {
    "psychologist": "Ты клинический психолог. Анализируй паттерны мышления, эмоциональные циклы...",
    "coach": "Ты ICF-коуч. Фокус на задачах, прогрессе, blockers...",
    "pattern_detector": "Ты аналитик поведенческих паттернов. Ищи повторяющиеся темы...",
    "devil_advocate": "Ты критик. Что пользователь не замечает? Что льстит сам себе?",
    "future_predictor": "Ты системный аналитик. Куда ведут текущие тренды?",
}

async def analyze_with_ensemble(day_text: str) -> MultiPerspectiveAnalysis:
    results = await asyncio.gather(*[
        call_analyst(role, prompt, day_text)
        for role, prompt in ANALYSTS.items()
    ])
    return synthesize_insights(results)
```

---

## 7. МУЛЬТИ-СЕНСОРНАЯ ИНТЕГРАЦИЯ

### 7.1 Дорожная карта источников данных

| Источник | Статус | Приоритет |
|---------|--------|-----------|
| Голос (основной) | ✅ Работает | — |
| Умные часы (шаги, пульс, сон) | ❌ Нет | HIGH |
| Геолокация | ❌ Нет | MEDIUM |
| Телефонные звонки (meta, не контент) | ❌ Нет | MEDIUM |
| Calendar события | ❌ Нет | HIGH |
| Whisper prosody (openSMILE) | ❌ Нет | HIGH |

### 7.2 Google Fit / Health Connect API (Android)

```kotlin
// HealthConnectClient
// Permissions: READ_STEPS, READ_HEART_RATE, READ_SLEEP_SESSION
// Sync каждые 6 часов → POST /health/metrics

data class DailyHealthMetrics(
    val date: String,
    val steps: Int,
    val avgHeartRate: Int,
    val sleepHours: Float,
    val stressLevel: Float?  // из пульса вариабельности
)
```

**Корреляция с речью:**
```
Sleep < 6h → утром больше негативных эмоций? (проверяемая гипотеза)
Steps < 2000 → меньше энергии в речи?
Пульс > 100 во время записи → тревожность?
```

### 7.3 openSMILE — Просодический анализ

```python
# Анализ ДО транскрипции (на уровне WAV файла):
# - Jitter (тремор голоса) → тревога
# - Shimmer (неравномерность амплитуды) → усталость
# - F0 (основной тон) → вопрос vs утверждение
# - Speech rate → возбуждённость

# Подключение через:
pip install opensmile
```

**Интеграция в pipeline:**
```
WAV → P0: SpeechFilter → openSMILE → prosody_features → Whisper → enrichment
                                           ↓
                         structured_events.prosody_json = {...}
```

### 7.4 Calendar Integration

```python
# Google Calendar API → получать события дня
# → добавлять в контекст enrichment:
# "Сегодня: 09:00 Standup, 14:00 Встреча с CEO, 18:00 Тренировка"
# → LLM видит контекст → лучше классифицирует
```

---

## 8. ПРОИЗВОДИТЕЛЬНОСТЬ И МАСШТАБИРОВАНИЕ

### 8.1 ASR оптимизация

**Текущее:** Whisper medium, CPU, int8
**Проблема:** ~5-10× реального времени = 30-сек сегмент обрабатывается 3-6 минут

**Опции (от лучшего к быстрому):**

| Вариант | WER | Скорость | Требования |
|---------|-----|----------|-----------|
| Whisper medium, CPU int8 | ~8% (ru) | ~5-10x | Текущее |
| Whisper medium, RTX 5070 Ti | ~8% (ru) | ~50x | GPU passthrough Docker |
| Whisper large-v3, GPU | ~5% (ru) | ~25x | GPU + 8GB VRAM |
| WhisperX large-v3 + diarization | ~5% + speaker ID | ~20x | GPU + 10GB VRAM |
| Parakeet v2 (nvidia) | ~3% (en only) | ~100x | GPU, only English |

**Рекомендация:** Переключить на GPU в Docker:
```yaml
# docker-compose.yml
services:
  api:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - ASR_DEVICE=cuda
      - ASR_COMPUTE_TYPE=float16
      - ASR_MODEL_SIZE=large-v3
```

### 8.2 LLM оптимизация

**Текущее:** gpt-4o-mini для enrichment (каждый сегмент) + digest

**Проблема:** При 50+ сегментах/день = $0.50-2.00/день только на enrichment

**Оптимизация:**
- Batching: группировать 5-10 коротких сегментов в один LLM запрос
- Кэширование топиков: если топик уже встречался → re-use
- Claude Haiku вместо gpt-4o-mini (в 3× дешевле, сравнимое качество для кратких текстов)
- Digest: один большой запрос вместо N маленьких

### 8.3 Database

**SQLite ограничения:**
- WAL mode включить: `PRAGMA journal_mode=WAL`
- Индексы на `created_at` (уже есть), добавить на `sentiment`, `urgency`, `domains`
- Для production: Supabase (pgvector для Stage-2 памяти)

---

## 9. БЕЗОПАСНОСТЬ И ПРИВАТНОСТЬ

### 9.1 Уровни приватности

| Режим | Описание | Когда использовать |
|-------|---------|-------------------|
| `strict` | Блокирует запись с PII | Публичные встречи |
| `mask` | Маскирует PII: "Иван" → "[PERSON]" | Рабочие разговоры |
| `audit` | Сохраняет оригинал + логирует PII | Личное использование |

**Текущее:** PRIVACY_MODE=audit ✅

### 9.2 Integrity Chain

SHA-256 hash chain обеспечивает:
- Неизменяемость записей после сохранения
- Обнаружение подмены данных
- Audit trail для каждого ingest_id

**Сохраняется:** `integrity_events` таблица. Доступ: `GET /audit/trail/{ingest_id}`

### 9.3 Что НЕ делается (и правильно)

- ❌ Биометрия не сохраняется в облако
- ❌ Аудиофайлы удаляются после транскрипции (P2 сервер + P3 телефон)
- ❌ ИИН/БИН/номера карт не в логах (PII detection)
- ❌ Supabase ключи только через env vars

### 9.4 Supabase RLS (требует настройки)

```sql
-- Включить Row Level Security
ALTER TABLE transcriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE structured_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_nodes ENABLE ROW LEVEL SECURITY;

-- Пользователь видит только свои данные
CREATE POLICY "user_own_data" ON transcriptions
    FOR ALL USING (auth.uid() = user_id);
```

---

## 10. ANDROID ROADMAP

### 10.1 Текущее состояние

| Компонент | Статус |
|-----------|--------|
| AudioRecordingService (foreground, VAD) | ✅ Работает |
| IngestWebSocketClient | ✅ Работает |
| P3: удаление WAV после upload | ✅ Работает |
| EnrichmentApiClient (2 попытки) | ✅ Работает |
| Room DB (Recording) | ✅ Работает |
| Compose UI (список, аналитика) | ✅ Базовое |
| Offline queue | ❌ Нет |
| WorkManager background sync | ❌ Нет |
| Колесо баланса UI | ❌ Нет |
| Push notifications | ❌ Нет |
| Настройки пользователя | ❌ Нет |

### 10.2 Приоритеты Android

**P0: Offline queue + retry**
```kotlin
@Entity
data class PendingUpload(
    val id: Long = 0,
    val filePath: String,
    val createdAt: Long,
    var retryCount: Int = 0,
    var lastError: String? = null
)

// WorkManager job: NetworkType.CONNECTED, BATTERY_NOT_LOW
class UploadWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params)
```

**P1: Wheel of Balance UI**
```kotlin
@Composable
fun BalanceWheelScreen() {
    // Spider chart (8 спиц)
    // Tap на домен → детали записей
    // Weekly trend chart
}
```

**P2: Battery optimization**
```
Текущее: delay(5) между фреймами = постоянный CPU
Нужно: AudioRecord setPositionNotificationPeriod() для callback-based чтения
```

**P3: Notification содержание**
```kotlin
// Обновить notification: "Reflexio: 47 сегментов записано, 3 задачи"
// Вместо: "Recording audio in background…"
```

---

## 11. DAILY DIGEST — ПОЛНАЯ СПЕЦИФИКАЦИЯ

### 11.1 Структура дайджеста

```markdown
# Reflexio Дайджест — 25 февраля 2026

## Краткое резюме
[CoD: 3-5 предложений, суть дня]

## Колесо Баланса
[Spider chart / text representation]
💼 Работа 8.2/10 | 🧠 Психология 3.1/10 | 🏃 Здоровье 1.1/10 ...

## Ключевые темы дня
1. [тема] — [краткое описание]
2. ...

## Эмоции дня
Доминирующие: [список]
Тренд: [Утро: нейтрально → После обеда: стресс → Вечер: спокойно]

## Задачи
### Упомянутые сегодня:
- [ ] задача 1 (urgent)
- [ ] задача 2

### Вчерашние (не закрыты):
- [ ] задача из вчера

## Инсайты (от 100 мудрецов)
> [Психолог]: Ты сегодня 3 раза использовал слово "должен" — это признак внешнего давления.
> [Коуч]: Из 8 задач озвучена только 1 с дедлайном.
> [Критик]: Ты говорил что "всё хорошо" но тон голоса не совпадает.

## Момент дня
[Самая эмоционально насыщенная запись дня]

## Рекомендация на завтра
[Одно конкретное действие]
```

### 11.2 Алгоритм генерации (tiered)

```python
async def generate_daily_digest(date: date) -> DigestResult:
    # Step 1: Загрузить все transcriptions за день
    all_records = get_day_records(date)  # без лимита 100

    # Step 2: Hourly summaries (параллельно)
    hours = group_by_hour(all_records)
    hourly_summaries = await asyncio.gather(*[
        summarize_hour(records, hour)
        for hour, records in hours.items()
    ])

    # Step 3: Domain analysis
    domain_stats = DomainClassifier().analyze_day(all_records)

    # Step 4: Linguistic markers
    psych_analysis = analyze_linguistic_markers(all_text)

    # Step 5: Daily digest из hourly summaries (не из сырых записей)
    digest = await generate_cod_digest(
        hourly_summaries=hourly_summaries,
        domain_stats=domain_stats,
        psych_analysis=psych_analysis,
        model="claude-3-haiku"
    )

    # Step 6: Critic validation
    validated = await critic_validate(digest)

    return validated
```

### 11.3 Endpoint для Telegram бота

```python
# 22:50 — автоматическая генерация
# GET /digest/daily?date=2026-02-25&format=telegram

# Telegram формат: markdown без HTML, лимит 4096 символов
# Если > 4096 → разбивать на 2-3 сообщения
```

---

## 12. КОНФИГУРАЦИЯ И РАЗВЕРТЫВАНИЕ

### 12.1 .env (production)

```env
# API
API_KEY=<strong-random-key>
API_HOST=0.0.0.0
API_PORT=8000

# ASR
ASR_MODEL_SIZE=large-v3
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=float16
ASR_LANGUAGE=  # пусто = auto-detect

# LLM
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<key>
LLM_MODEL_ACTOR=claude-3-haiku-20240307
LLM_MODEL_CRITIC=claude-3-haiku-20240307

# Storage
DB_BACKEND=supabase
SUPABASE_URL=<url>
SUPABASE_ANON_KEY=<key>
SUPABASE_SERVICE_KEY=<key>

# Filters
FILTER_MUSIC=true
FILTER_METHOD=fft

# Privacy
PRIVACY_MODE=audit
INTEGRITY_CHAIN_ENABLED=true

# Features
MEMORY_ENABLED=true
RETRIEVAL_ENABLED=true
EXTENDED_METRICS=true

# Bot
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>
```

### 12.2 docker-compose.yml (production)

```yaml
services:
  api:
    build: .
    container_name: reflexio-api
    ports: ["8000:8000"]
    env_file: [.env]
    environment:
      - FILTER_MUSIC=true
      - ASR_DEVICE=cuda
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    volumes:
      - ./src/storage:/app/src/storage
      - ./config:/app/config
      # НЕ монтируем ./src:/app/src в production
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    # Для rate limiting (RATE_LIMIT_STORAGE=redis)
```

### 12.3 Android BuildConfig

```kotlin
// build.gradle.kts
buildConfigField("String", "SERVER_WS_URL", "\"ws://10.0.2.2:8000\"")
buildConfigField("String", "SERVER_WS_URL_DEVICE", "\"ws://192.168.1.X:8000\"")
buildConfigField("String", "SERVER_API_KEY", "\"${localProperties.getProperty("server.api.key", "")}\"")
```

---

## 13. КЛЮЧЕВЫЕ МЕТРИКИ УСПЕХА

### 13.1 Технические KPI

| Метрика | Цель | Текущее |
|---------|------|---------|
| ASR WER (русский) | < 10% | ~8% (medium) |
| Enrichment latency | < 3 сек | ~1-2 сек |
| Noise filter FPR | < 2% | ~0% (может пропускать) |
| Noise filter FNR | < 5% | Неизвестно |
| Digest generation time | < 30 сек | ~10-15 сек |
| Android crash rate | < 0.1% | Неизвестно |
| Upload success rate | > 99% | ~95% (нет offline queue) |
| DB size/день | < 50MB | ~5MB |

### 13.2 Продуктовые KPI

| Метрика | Цель |
|---------|------|
| Digest read rate | > 80% дней |
| Digest action rate | ≥ 1 задача выполнена из дайджеста/неделю |
| Balance wheel accuracy | Пользователь согласен с 70%+ классификаций |
| Insight "aha moment" | ≥ 1 неожиданный инсайт/неделю |

---

## 14. ФАЙЛОВАЯ СТРУКТУРА ПРОЕКТА

```
D:/24 na 7/
├── src/
│   ├── api/
│   │   ├── main.py                    # FastAPI app, middleware, startup
│   │   ├── middleware/                # auth, safe, input_guard
│   │   └── routers/
│   │       ├── websocket.py           # Core WS pipeline (P0-P3)
│   │       ├── ingest.py              # REST upload (needs sync with WS)
│   │       ├── digest.py              # Digest endpoints
│   │       ├── memory.py              # /memory/search
│   │       ├── audit.py               # /audit/trail
│   │       └── enrichment.py          # /enrichment/{file_id}
│   ├── asr/
│   │   ├── transcribe.py              # Multi-provider ASR
│   │   └── providers.py               # OpenAI/WhisperX/Parakeet/Local
│   ├── enrichment/
│   │   ├── enricher.py                # enrich_transcription()
│   │   └── schema.py                  # StructuredEvent Pydantic model
│   ├── digest/
│   │   ├── generator.py               # DigestGenerator (CoD + Critic)
│   │   └── analyzer.py                # InformationDensityAnalyzer
│   ├── memory/
│   │   └── semantic_memory.py         # memory_nodes CRUD + retrieval
│   ├── storage/
│   │   ├── ingest_persist.py          # SQLite: ingest_queue + transcriptions
│   │   └── integrity.py               # SHA-256 hash chain
│   ├── security/
│   │   └── privacy_pipeline.py        # PII detection (strict/mask/audit)
│   ├── summarizer/
│   │   ├── few_shot.py                # analyze_recording_text()
│   │   └── prompts.py                 # Prompt templates
│   ├── llm/
│   │   ├── providers.py               # OpenAI/Anthropic/Gemini clients
│   │   └── schemas/                   # Pydantic schemas для LLM
│   ├── utils/
│   │   ├── config.py                  # Settings (Pydantic BaseSettings)
│   │   ├── logging.py                 # structlog setup
│   │   └── guardrails.py              # PIIDetector
│   └── storage/
│       ├── uploads/                   # Temp WAV files (auto-deleted)
│       ├── recordings/                # Processed files
│       └── recordings.db              # SQLite database
│
├── android/
│   └── app/src/main/kotlin/com/reflexio/app/
│       ├── domain/
│       │   ├── services/AudioRecordingService.kt   # Foreground service, VAD
│       │   ├── network/IngestWebSocketClient.kt     # WS binary upload
│       │   ├── network/EnrichmentApiClient.kt       # HTTP enrichment fetch
│       │   └── vad/VadSegmentWriter.kt              # webrtcvad wrapper
│       ├── data/
│       │   ├── db/RecordingDatabase.kt              # Room DB
│       │   ├── db/RecordingDao.kt                   # DAO
│       │   └── model/Recording.kt                   # Data model
│       └── ui/
│           ├── MainActivity.kt
│           └── screens/                             # Compose screens
│
├── config/
│   └── asr.yaml                       # ASR provider config
├── migrations/
│   └── *.sql                          # DB migrations
├── tests/
├── docker-compose.yml
├── Dockerfile.api
├── .env                               # Secrets (не в git)
└── CLAUDE.md                          # Проектные инструкции
```

---

## 15. СЛЕДУЮЩИЕ ШАГИ (ORDERED BY PRIORITY)

### Немедленно (эта неделя):
1. **Fix CoD** — tiered chunking в `digest/generator.py`
2. **Русские стоп-фразы** — добавить в `websocket.py` и `enricher.py`
3. **topics/domains разделение** — ALTER TABLE + DomainClassifier скелет
4. **Убрать SAFE checker warning** — создать `src/validation/safe_checker.py`

### На следующей неделе:
5. **Android offline queue** (WorkManager + Room PendingUpload)
6. **Retry для async enrichment** (3 попытки exponential backoff)
7. **GPU ASR** (если Docker GPU passthrough работает на RTX 5070 Ti)
8. **Перенести CoreMemory** из .cursor/ в src/storage/

### В течение месяца:
9. **Wheel of Balance API** + Android UI
10. **Supabase RLS** настроить
11. **Stage-2 память** (text-embedding-3-small + pgvector)
12. **openSMILE** просодический анализ

### Долгосрочно (3-6 месяцев):
13. **PersonGraph** (Graphiti + temporal KG)
14. **Health Connect** интеграция (шаги, сон, пульс)
15. **"100 мудрецов"** — ансамбль аналитиков
16. **Calendar API** контекст для enrichment

---

*Документ создан: 2026-02-25. Обновлять после каждого значимого архитектурного решения.*
