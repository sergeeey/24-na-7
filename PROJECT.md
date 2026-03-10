# Reflexio 24/7 — Project Documentation

> **Версия:** 0.4.0 | **Дата:** 2026-03-04 | **Статус:** Production (Beta)
> **VPS:** reflexio247.duckdns.org | **SSH:** `root@46.225.211.115` | **Репо:** github.com/sergeeey/24-na-7

---

## Что это

**Reflexio** — персональный AI-ассистент непрерывного наблюдения за речью.
Приложение работает фоном на Android, записывает речь сегментами по 3 секунды через VAD, транскрибирует через Whisper, обогащает через LLM (эмоции, темы, задачи) и к вечеру генерирует дайджест дня с инсайтами, паттернами и рекомендациями.

**Ключевая идея:** не заметки голосом, а пассивная цифровая память — пользователь ничего не нажимает, система сама слушает и структурирует.

**One Interface (v0.3.0):** один вопрос на естественном языке → `POST /ask` → Orchestrator выбирает нужные тулы → синтезированный ответ с уровнем уверенности.

**Visual Memory (v0.4.0):** ответ несёт `UIHint` (подсказка рендеринга) и `evidence_metadata` (временные якоря событий). Android показывает EvidenceTraceRow — горизонтальный таймлайн улик со sentiment-цветом.

---

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│                  Android (Kotlin)                    │
│  VAD → WebSocket binary stream                       │
│  AskScreen → POST /ask (One Interface)               │
│  NavigationBar: Спросить│Запись│Итог│Аналитика│Голос │
└────────────────────┬────────────────────────────────┘
                     │ WSS / HTTPS
┌────────────────────▼────────────────────────────────┐
│              Caddy (reverse proxy + SSL)             │
│              reflexio247.duckdns.org                 │
└────────────────────┬────────────────────────────────┘
                     │ HTTP localhost:8000
┌────────────────────▼────────────────────────────────┐
│           FastAPI (2 uvicorn workers)                │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │  Query Engine v1.0                          │    │
│  │  POST /ask → Orchestrator → ToolResult[]    │    │
│  │  ConfidencePolicy → answer + confidence     │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
│  WebSocket → Pipeline → ASR → Enrichment → Storage  │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ SQLite   │  │  Redis   │  │  APScheduler     │  │
│  │+SQLCipher│  │rate limit│  │  18:00 digest    │  │
│  └──────────┘  └──────────┘  │  03:00 cleanup   │  │
│                               └──────────────────┘  │
└─────────────────────────────────────────────────────┘
         VPS: Hetzner CX33 — 4 vCPU / 8 GB RAM / 40 GB SSD
```

---

## Pipeline (аудио → событие)

```
Android Pixel 9 Pro
  → VAD (3-сек сегменты, webrtcvad)
  → WebSocket binary upload

Server:
  1. SpeechFilter: FFT — речь 300-3400 Hz vs музыка >4 kHz → отсеиваем шум/музыку
  2. SAFE check: размер ≤ 25 MB, input validation
  3. SpeakerVerification: resemblyzer GE2E ~50 ms — опционально (SPEAKER_VERIFICATION_ENABLED)
  4. Diarize: pyannote.audio → DiarizedSegment[] — опционально (HF_TOKEN required)
  5. AcousticFeatures: pitch (YIN), RMS energy, spectral centroid, arousal (high/normal/low)
  6. Whisper medium: language=ru, CPU int8 — транскрипция
  7. Filter: минимум 3 слова, не стоп-фразы (угу/ага/hmm...), lang_prob > 0.4
  8. NameAnchorExtractor → VoiceProfileAccumulator → Social Graph
  9. Privacy pipeline: audit mode (PII не маскируется, но логируется)
 10. SQLite persist + integrity chain (SHA-256 хэши)
 11. WAV удалён на сервере → "delete_audio:true" → WAV удалён на телефоне
 12. Enrichment (async worker):
       LLM Cascade: Gemini Flash (free) → Claude Haiku → GPT-4o-mini
       → topics, emotions, tasks, decisions, summary, sentiment, urgency
       → prompt_hash (SHA-256[:12]) + enrichment_version ("2.1.0")
 13. sqlite-vec: cosine embedding (OpenAI text-embedding-3-small, dim=1536)
 14. Event Log: AUDIO_RECEIVED → ASR_DONE → ENRICHED (latency_ms каждой стадии)

APScheduler:
  18:00 Almaty (12:00 UTC): pre-compute digest → digest_cache → ответ <1 сек
  03:00: compliance_cleanup (TTL биометрических данных, KZ GDPR)
```

---

## Query Engine v1.0

### Архитектура (rule-based, без LLM)

```
POST /ask {"question": "что было сегодня?"}
     ↓
analyze_intent()          # rule-based regex, <5ms, покрывает 90% вопросов
     ↓
ToolCall[]                # [get_digest, query_events] или [get_person_insights]
     ↓
asyncio.gather()          # параллельный вызов всех тулов
     ↓
merge_confidence()        # weighted average по evidence_count
     ↓
synthesize_response()     # минимальный текстовый ответ
     ↓
OrchestratorResponse {answer, data[], confidence, confidence_label,
                       evidence_count, tools_used, total_ms}
```

**Latency target:** ≤400 ms (без LLM-запросов в оркестраторе)

### ToolResult — единый контракт ответа

```python
ToolResult(
    data=Any,
    evidence_ids=["event-uuid-1", ...],  # доказательная база
    confidence=0.85,                      # 0.0–1.0
    confidence_label="high",              # авто-выводится из score
    tool_name="query_events",
    db_query_ms=42.0,
    error=None,
    warning=None,
    # v0.4.0 Visual Memory:
    ui_hint=UIHint.TIMELINE,             # TIMELINE|PERSON_GRAPH|ACTION_LIST|CARD|LIST
    evidence_metadata=[                  # temporal anchors для EvidenceTraceRow
        {"id": "...", "timestamp": "...", "sentiment_score": 0.5, "top_topic": "работа"}
    ],
)
```

**UIHint — rendering contract:**
| Value | Когда | Android рендер |
|-------|-------|----------------|
| `timeline` | События по времени (default) | EvidenceTraceRow |
| `action_list` | Есть tasks в events | ActionList |
| `person_graph` | Запрос про персону | PersonGraph |
| `card` | Одиночный факт | Card |
| `list` | Простой список | List |

### Confidence Policy (4 уровня)

| Label | Score | UI | Смысл |
|-------|-------|----|-------|
| `high` | ≥ 0.8 | Зелёный | Прямой ответ, ≥2 evidence |
| `medium` | 0.6–0.79 | Синий | Аккуратный ответ |
| `low` | 0.4–0.59 | Оранжевый | Есть признаки, но неполно |
| `speculative` | < 0.4 | Красный | Предположение, нужно уточнение |

**Авто-даунгрейд:** HIGH confidence с < 2 evidence → автоматически понижается до MEDIUM.

### Инструменты оркестратора

| Тул | Endpoint | Когда |
|-----|----------|-------|
| `query_events` | `GET /query/events` | Семантический поиск по вопросу (fallback) |
| `get_digest` | `GET /query/digest` | Ключевые слова: дайджест/итог/recap/сегодня/вчера |
| `get_person_insights` | `GET /query/person/{name}` | Вопрос про конкретного человека |
| `add_manual_note` | `POST /query/note` | WRITE операция (требует permission token) |
| `trigger_digest_generation` | `POST /query/digest/generate` | Принудительная генерация (IRREVERSIBLE) |

### Permission Gate

Защита деструктивных операций (WRITE/IRREVERSIBLE):
```
1. Первый запрос → 422 {requires_confirmation: true, token: "sha256[:32]", expires_in: 60}
2. Повторный запрос с X-Confirm-Token → выполняется (token одноразовый, TTL 60 сек)
3. Аудит: каждая WRITE операция логируется в event_log
```

Хранилище: Redis (производство) + in-memory dict (fallback).

---

## Модули Backend (src/)

| Модуль | Описание |
|--------|----------|
| `api/` | FastAPI routers + 3 middleware (auth, input_guard, SAFE) |
| `api/middleware/permission_gate.py` | Confirmation token (SHA-256, TTL 60s, one-time use) |
| `asr/` | Whisper wrapper, acoustic features (librosa/YIN), diarize (pyannote) |
| `core/tool_result.py` | ToolResult контракт + ConfidenceLabel + add_meta() + ToolTimer |
| `core/confidence.py` | merge_confidence() + single_confidence() — агрегация уверенности |
| `core/orchestrator.py` | Rule-based intent analysis + параллельный вызов тулов + синтез |
| `core/audio_processing.py` | Оркестратор аудио pipeline |
| `core/bootstrap.py` | Lifespan FastAPI, APScheduler, ingest/enrichment workers, zero-retention watchdog-и |
| `digest/` | Chain of Density summarizer, critic, PDF генератор, Telegram sender |
| `edge/` | VAD v2, speech filters (FFT), edge listener |
| `enrichment/` | Async worker, LLM enricher, StructuredEvent schema |
| `llm/` | Cascade client (Gemini→Haiku→GPT-4o-mini), circuit breakers, prompt manager |
| `memory/` | Core memory, session memory, semantic retrieval |
| `persongraph/` | KùzuDB embedded graph (multi-hop path finding, clusters) |
| `speaker/` | Voice enrollment, resemblyzer GE2E speaker verification |
| `storage/` | SQLite/SQLCipher DB, migrations (0001-0013), vec_search, event_log, digest_lineage |
| `balance/` | Колесо баланса (Balance Wheel — 8 жизненных сфер) |
| `summarizer/` | Chain of Density, critic validator, few-shot (tasks, emotions) |
| `security/` | Crypto helpers, PII detection |
| `utils/config.py` | Pydantic-settings (Settings) |
| `utils/date_utils.py` | resolve_date_range() — timezone-aware (UTC+6 Almaty), DateRange |
| `utils/logging.py` | structlog |
| `utils/rate_limiter.py` | RateLimitConfig + setup_rate_limiting() |
| `experimental/` | Карантин для R&D (voice_agent, explainability и другие экспериментальные подсистемы) |

---

## API Endpoints

### One Interface (v0.3.0)
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| POST | `/ask` | 10/min | Оркестратор: вопрос → авто-выбор тулов → ответ с confidence |

### Query Engine
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| GET | `/query/events` | 30/min | Семантический поиск (date, topics, emotions, min_confidence) |
| GET | `/query/digest` | 20/min | Дайджест (из кеша или inline генерация) |
| GET | `/query/person/{name}` | 30/min | Инсайты по персоне (граф + взаимодействия) |
| POST | `/query/note` | 5/min | Добавить заметку (permission gate) |
| POST | `/query/digest/generate` | 2/min | Принудительная генерация дайджеста (IRREVERSIBLE, permission gate) |

### Core
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| GET | `/health` | — | Health check (`{"status":"ok","version":"0.4.0"}`) |
| POST | `/ingest/audio` | 10/min | Загрузка аудио файла |
| WS | `/ws/audio` | — | WebSocket стриминг с Android |

### Digest
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| GET | `/digest/daily` | 30/min | Дайджест дня (кеш → pending → inline) |
| GET | `/digest/today` | 20/min | Сегодняшний дайджест |
| GET | `/digest/{date}` | 20/min | Дайджест за дату (YYYY-MM-DD) |
| GET | `/digest/{date}/sources` | 60/min | GDPR audit trail |
| GET | `/digest/{date}/density` | 10/min | Анализ информационной плотности |

### Search & Observability
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| GET | `/search/events` | 30/min | Семантический поиск (cosine, sqlite-vec) `+_meta` |
| POST | `/search/phrases` | 30/min | Поиск по фразам |
| POST | `/search/reindex` | 2/min | Переиндексация (admin) |
| GET | `/search/trace/{id}` | 60/min | Lifecycle одного аудио (все стадии + latency_ms) |
| GET | `/search/errors` | 30/min | Мониторинг ошибок pipeline |

### Balance Wheel
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| GET | `/balance/wheel` | 30/min | Колесо баланса по дате `+_meta` |
| GET | `/balance/domains` | 60/min | Список конфигураций сфер |
| POST | `/balance/domains` | 10/min | Создать/обновить сферу |
| PUT | `/balance/domains/{d}` | 10/min | Обновить сферу |
| GET | `/balance/insights` | 30/min | Инсайты за день |

### Social Graph
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| GET | `/graph/persons` | 50/min | Список людей из окружения |
| GET | `/graph/persons/{name}` | 50/min | Детали персоны |
| GET | `/graph/pending` | 50/min | Ожидают подтверждения голосового профиля |
| POST | `/graph/approve/{name}` | 10/min | Подтвердить профиль (+ Kuzu sync) |
| POST | `/graph/reject/{name}` | 10/min | Отклонить (немедленное удаление) |
| GET | `/graph/stats` | 50/min | Статистика графа |
| GET | `/graph/neighborhood/{name}?hops=2` | 30/min | Граф соседей (KùzuDB→SQLite fallback) *(v0.4.0)* |

### Compliance (KZ GDPR)
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| GET | `/compliance/status` | 30/min | TTL-статистика биометрических данных |
| DELETE | `/compliance/erase/{person}` | 5/min | Право быть забытым (ст. 20 Закона РК) |
| POST | `/compliance/run-cleanup` | 5/min | Ручной запуск TTL-очистки |

### Analytics, Health, ASR, Voice
| Метод | Endpoint | Rate | Описание |
|-------|----------|------|----------|
| POST | `/asr/transcribe` | 10/min | Транскрипция файла по ID |
| POST | `/analyze/text` | 10/min | LLM-анализ текста (topics, emotions, urgency) |
| POST | `/health/metrics` | 30/min | Ingestion метрик со смартфона |
| GET | `/health/metrics` | 60/min | Чтение health-метрик |
| GET | `/metrics` | 60/min | Системные метрики |
| GET | `/metrics/prometheus` | 60/min | Prometheus-совместимый формат |
| GET | `/memory/retrieve` | 20/min | Семантический retrieval из memory store |
| GET | `/audit/ingest/{id}` | 60/min | Integrity chain отчёт |
| POST | `/voice/intent` | 20/min | Распознавание intent (Voiceflow RAG) |
| POST | `/voice/enroll` | 5/min | Голосовой enrollment (3+ WAV файла) |
| GET | `/voice/enroll/status` | 30/min | Статус голосового профиля |

---

## Android (Kotlin / Jetpack Compose)

**Min SDK:** 26 | **Target SDK:** 34 | **AGP:** 8.2.2

### Экраны (NavigationBar — 5 табов)

| # | Экран | Назначение |
|---|-------|------------|
| 0 | `AskScreen` ⭐ | **One Interface** — вопрос → POST /ask → ответ с ConfidenceBadge |
| 1 | `HomeScreen` | Колесо баланса + кнопка записи |
| 2 | `DailySummaryScreen` | Дайджест дня (FlowRow chips, интерактивные задачи) |
| 3 | `AnalyticsScreen` | Аналитика паттернов и эмоций |
| 4 | `VoiceEnrollmentScreen` | Запись голосового профиля (3+ WAV, 60 сек timeout) |

### AskScreen — One Interface

```
┌─────────────────────────────────────┐
│ OutlinedTextField (2-4 строки)       │
│ "Спроси что угодно о своём дне…"    │
│                        [Спросить 🔍] │
├─────────────────────────────────────┤
│ 🟢 Высокая уверенность · 87%        │  ← ConfidenceBadge (v0.4.0: пульсирует для speculative)
├─────────────────────────────────────┤
│ Найдено 5 событий о стрессе.        │  ← answer text
│ Последнее — 14:32 о дедлайне.       │
├─────────────────────────────────────┤
│ [14:32·стресс·🔴] [15:10·работа·🟡] │  ← EvidenceTraceRow (v0.4.0)
│ [16:45·финансы·🟢]                  │
├─────────────────────────────────────┤
│                   [Детали ▼]         │
│  Улик найдено   8                    │
│  Время ответа   230 мс              │
│  Тулы           query_events        │
└─────────────────────────────────────┘
```

**ConfidenceBadge цвета:**
- `high` → зелёный `#4CAF50`
- `medium` → синий `#2196F3`
- `low` → оранжевый `#FF9800`
- `speculative` → красный `#F44336` + пульсирующая анимация (alpha 0.5→1.0, 800ms)

### Ключевые компоненты
- `BalanceWheelVisualizer` — GPU-accelerated визуализация 8 сфер жизни
- `ParticleFieldVisualizer` — 300 частиц с физикой (60 FPS)
- `AudioSpectrumAnalyzer` — FFT анализ (8 частотных полос)
- `PendingUpload` + `UploadWorker` — offline queue (Room DB → retry при сети)
- `EvidenceTraceRow` — горизонтальный LazyRow с temporal anchors (v0.4.0)
- `ConfidenceBadge` — пульсирующий badge для speculative уверенности (v0.4.0)

### Сетевой стек
- WebSocket: binary audio streaming (VAD сегменты 3 сек)
- HTTP: OkHttp (30 сек timeout digest, 60 сек enrollment, 10/30 сек ask)
- Network security config: prod HTTPS/WSS, debug HTTP/WS

---

## База данных (SQLite + SQLCipher AES-256)

**Файл:** `storage/reflexio.db` | **WAL mode** | **Шифрование:** AES-256-CBC

### Ключевые таблицы
| Таблица | Назначение |
|---------|------------|
| `ingest_queue` | Входящие аудио файлы и статус обработки |
| `transcriptions` | Результаты ASR (текст, уверенность, язык) |
| `structured_events` | Enriched события (topics, emotions, tasks, acoustic features) |
| `integrity_events` | SHA-256 хэш-цепочка для аудита |
| `event_log` | Observability log (AUDIO_RECEIVED→ASR_DONE→ENRICHED→DIGEST) |
| `vec_events` | Virtual table sqlite-vec (cosine embeddings dim=1536) |
| `digest_cache` | Pre-computed дайджесты (ответ <1 сек вместо 4+ мин) |
| `digest_sources` | GDPR lineage: digest_id → [event_id] |
| `persons` | Social graph (relationship, voice_ready, approved_at) |
| `person_voice_samples` | Голосовые образцы (status: accumulating→pending→approved) |
| `schema_migrations` | История миграций (`INSERT OR IGNORE` — защита от race condition 2 workers) |

### Миграции
- 0001–0009: PostgreSQL-совместимые (legacy)
- 0010–0013: SQLite-специфичные (digest_cache, acoustic, vec, missing_tables)
- 0014: digest_sources (GDPR lineage)
- 0015: индексы для UIHint/EvidenceTrace (acoustic_arousal, sentiment+created_at, person+created_at)

---

## LLM Stack

### Cascade (приоритет по стоимости)
```
1. Google Gemini Flash  — бесплатно (основной)
2. Claude Haiku         — $0.25/1M tokens (fallback)
3. GPT-4o-mini          — $0.15/1M tokens (резервный fallback)
```
- Circuit breaker: 5 ошибок → 60 сек пауза для каждого провайдера
- `LLM_CASCADE_ORDER=google,anthropic,openai` в .env

### Enrichment output (StructuredEvent)
```python
topics: list[str]           # ["работа", "финансы"]
emotions: list[str]         # ["тревога", "решимость"]
tasks: list[TaskExtracted]  # [{text, priority, deadline}]
decisions: list[str]        # ["купить...", "позвонить..."]
sentiment: str              # positive | neutral | negative
urgency: str                # low | medium | high
acoustic_arousal: str       # low | normal | high (из DSP, не LLM)
pitch_hz_mean: float        # объективные данные голоса
enrichment_prompt_hash: str # SHA-256[:12] → аудит drift промпта
enrichment_version: str     # "2.1.0"
```

---

## Инфраструктура

| Компонент | Детали |
|-----------|--------|
| **VPS** | Hetzner CX33 — 4 vCPU, 8 GB RAM, 40 GB SSD / €5.99/мес |
| **Domain** | reflexio247.duckdns.org (DuckDNS, бесплатно) |
| **SSL** | Caddy automatic (Let's Encrypt) |
| **Proxy** | Caddy → localhost:8000 |
| **App** | 2 uvicorn workers (Whisper CPU-блокирует → нужен второй worker для REST) |
| **Cache** | Redis 7 alpine (rate limiting counters, permission gate tokens) |
| **Build** | Docker multi-stage (builder+gcc, runtime без компилятора, ~400 MB экономии) |
| **Deploy** | `git pull` + `docker compose restart` (./src монтируется → без rebuild) |
| **SSH** | `ssh root@46.225.211.115` (ed25519 key) |

### Обновление кода на проде
```bash
ssh root@46.225.211.115
cd /opt/reflexio
git pull origin main
docker compose -f docker-compose.prod.yml restart api
```

### Полный rebuild (при изменении requirements.txt или Dockerfile)
```bash
docker compose -f docker-compose.prod.yml down
docker system prune -af   # освободить место (~15 GB)
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Безопасность

| Уровень | Механизм |
|---------|----------|
| **Transport** | HTTPS/WSS через Caddy + Let's Encrypt |
| **Auth** | API Key (Bearer header + query param fallback с логированием) |
| **Rate Limiting** | 32 декоратора `@limiter.limit()` в 13 роутерах (slowapi + Redis in-memory) |
| **Permission Gate** | Confirmation token для WRITE/IRREVERSIBLE операций (SHA-256[:32], TTL 60s, one-time) |
| **Storage** | SQLCipher AES-256-CBC + file-based key fallback |
| **Input** | SAFE middleware (25 MB limit, audit mode), input_guard middleware |
| **PII** | Privacy pipeline audit mode; SQLCIPHER_KEY из env, не в коде |
| **Circuit Breakers** | 5 failures → 60s pause для каждого LLM провайдера |
| **Compliance** | KZ GDPR: TTL cleanup 03:00, `DELETE /compliance/erase/{person}` |
| **Integrity** | SHA-256 hash chain для каждой транскрипции |
| **API Keys** | Только в .env, никогда в коде; ротируются (score 10/10) |
| **Race Condition** | `INSERT OR IGNORE INTO schema_migrations` — 2 uvicorn workers не конфликтуют |

**Security Score: 10/10** (достигнут 2026-03-03)

### Rate Limits сводная таблица
| Операция | Лимит | Обоснование |
|----------|-------|-------------|
| Загрузка аудио | 10/min | Тяжёлый pipeline |
| Транскрипция ASR | 10/min | CPU-интенсив (Whisper) |
| LLM анализ | 10/min | Стоимость LLM вызовов |
| POST /ask | 10/min | Оркестратор (параллельные тулы) |
| Генерация дайджеста | 2-10/min | Долгая операция (2-5 мин) |
| Voice enrollment | 5/min | Тяжёлый embedding |
| Семантический поиск | 30/min | БД + vec операции |
| Health checks | 60-200/min | Лёгкие read-only |

---

## Тесты

```
595 passed, 24 skipped, 0 failed
```

```bash
# Запуск
python -m pytest tests/ -q --ignore=tests/e2e

# С coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```

**Ключевые test файлы:**
- `tests/test_coverage_95.py` — основное покрытие (1000+ строк)
- `tests/test_coverage_api_asr.py` — API + ASR интеграция
- `tests/test_semantic_search.py` — cosine similarity, hybrid search
- `tests/e2e/` — end-to-end (требуют запущенный сервер)

---

## Опциональные модули (не активированы)

### pyannote.audio (диаризация спикеров)
Определяет кто говорит — "Сергей", "коллега", "незнакомый".
```bash
# 1. Принять лицензию: huggingface.co/pyannote/speaker-diarization-3.1
# 2. Добавить в .env: HF_TOKEN=hf_xxx
# 3. Раскомментировать в requirements.txt: pyannote.audio>=3.1.0
# 4. docker compose -f docker-compose.prod.yml up -d --build
```

### KùzuDB (multi-hop граф) — активирован в v0.4.0
Встроенный граф-движок — shortest path, clusters, соседи за N hops.
- `kuzu>=0.7.0` раскомментирован в requirements.txt ✅
- `GET /graph/neighborhood/{name}?hops=2` — активен ✅
- Fallback: если kuzu недоступен → SQLite persons без multi-hop

---

## Дорожная карта

### v0.5.0 (следующий спринт)
- [ ] EWMA voice profile adaptation (адаптация к изменениям голоса)
- [ ] `speaker_score` поле в structured_events (float 0–1)
- [ ] Quarantine mode для non-owner аудио сегментов
- [ ] Docker health check timeout fix (увеличить в docker-compose.yml)
- [ ] Whisper worker memory leak watchdog (рестарт каждые N часов)
- [ ] E2E тесты для `/ask` + UIHint валидация

### v1.1
- [ ] Beta testing: 500 пользователей (referral + Product Hunt)
- [ ] Graph API: `/graph/paths`, `/graph/clusters`
- [ ] Активация pyannote.audio на проде

### v1.2
- [ ] English language support
- [ ] Slack integration (weekly digest в канал)
- [ ] Team edition (общий граф команды)

### v2.0
- [ ] Real-time insights (не дайджест раз в день, а push-уведомления)
- [ ] On-device ASR (Whisper.cpp Android, приватность)
- [ ] Локальный LLM (Ollama на RTX 5070 Ti)
- [ ] LLM-based intent analysis (fallback для сложных вопросов)

---

## Стек технологий

**Backend:** Python 3.11, FastAPI 0.110+, SQLite/SQLCipher, Redis, APScheduler, slowapi
**ML:** faster-whisper (Whisper medium), librosa (acoustic), resemblyzer (GE2E), sentence-transformers, sqlite-vec
**LLM:** Google Gemini Flash / Anthropic Claude Haiku / OpenAI GPT-4o-mini (cascade)
**Android:** Kotlin, Jetpack Compose, Room, WorkManager, OkHttp 4.12
**Infra:** Docker multi-stage, Caddy, Hetzner VPS
**Quality:** ruff, structlog, pydantic v2, pytest (595 tests)
**v0.4.0:** UIHint rendering contract, evidence_metadata temporal anchors, KùzuDB neighborhood graph, resemblyzer GE2E speaker verification

---

## Changelog

| Версия | Дата | Изменения |
|--------|------|-----------|
| 0.4.1 | 2026-03-10 | Архитектурный карантин: вынесены `src/voice_agent/*` и `src/explainability/*` в `src/experimental/*`, `api.main` использует `core.bootstrap.lifespan`, ядро `/ask` и пайплайн Edge→ASR→Digest изолированы от R&D модулей. |
| 0.4.0 | 2026-03-04 | Visual Memory: UIHint enum (rendering contract), evidence_metadata (temporal anchors), GET /graph/neighborhood (KùzuDB→SQLite fallback), migration 0015 (3 индекса). Android: EvidenceTraceRow + pulsating ConfidenceBadge. KùzuDB активирован. Voice enrollment (resemblyzer GE2E, 3 сэмпла). SPEAKER_VERIFICATION_ENABLED. |
| 0.3.0 | 2026-03-03 | Query Engine v1.0: ToolResult, Orchestrator, POST /ask, ConfidencePolicy, Permission Gate, date_utils. Rate limits: 32 декоратора в 13 роутерах. Android AskScreen (One Interface, таб 0). _meta миграция search/balance. |
| 0.2.0 | 2026-03-03 | Security hardening, migration 0013, docker env vars fix, missing Settings fields, migration race condition fix |
| 0.1.0 | 2026-02-xx | Initial production deploy: WebSocket pipeline, Whisper ASR, LLM enrichment, digest, social graph, compliance |
