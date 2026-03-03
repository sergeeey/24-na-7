# Reflexio 24/7 — Project Documentation

> **Версия:** 0.2.0 | **Дата:** 2026-03-03 | **Статус:** Production (Beta)
> **VPS:** reflexio247.duckdns.org | **Репо:** github.com/sergeeey/24-na-7

---

## Что это

**Reflexio** — персональный AI-ассистент непрерывного наблюдения за речью.
Приложение работает фоном на Android, записывает речь сегментами по 3 секунды через VAD, транскрибирует через Whisper, обогащает через LLM (эмоции, темы, задачи) и к вечеру генерирует дайджест дня с инсайтами, паттернами и рекомендациями.

**Ключевая идея:** не заметки голосом, а пассивная цифровая память — пользователь ничего не нажимает, система сама слушает и структурирует.

---

## Архитектура

```
┌─────────────────────────────────────────────────────┐
│                  Android (Kotlin)                    │
│  VAD → WebSocket binary stream → UI (Jetpack Compose)│
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

## Модули Backend (src/)

| Модуль | Описание |
|--------|----------|
| `api/` | FastAPI routers + 3 middleware (auth, input_guard, SAFE) |
| `asr/` | Whisper wrapper, acoustic features (librosa/YIN), diarize (pyannote) |
| `core/` | `audio_processing.py` — оркестратор всего pipeline |
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
| `utils/` | Config (pydantic-settings), logging (structlog), rate limiter, circuit breaker |

---

## API Endpoints

### Core
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/health` | Health check (`{"status":"ok","version":"0.2.0"}`) |
| POST | `/ingest/audio` | Загрузка аудио файла (sync обработка если INGEST_SYNC_PROCESS=1) |
| WS | `/ws/audio` | WebSocket стриминг аудио с Android |
| GET | `/digest/today` | Дайджест сегодняшнего дня (из кеша <1 сек) |
| GET | `/digest/{date}` | Дайджест за дату (YYYY-MM-DD) |
| GET | `/digest/{date}/sources` | GDPR audit trail — какие события вошли в дайджест |
| GET | `/balance/wheel` | Колесо баланса по дате |

### Search & Observability
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/search/events?q=...` | Семантический поиск (cosine similarity через sqlite-vec) |
| POST | `/search/reindex` | Переиндексация всех событий |
| GET | `/search/trace/{session_id}` | Lifecycle одного аудио (все стадии с latency_ms) |
| GET | `/search/errors` | Мониторинг ошибок pipeline |

### Social Graph
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/graph/persons` | Список людей из окружения (фильтры: relationship, voice_ready) |
| GET | `/graph/persons/{name}` | Детали персоны |
| GET | `/graph/pending` | Ожидают подтверждения голосового профиля |
| POST | `/graph/approve/{name}` | Подтвердить профиль |
| POST | `/graph/reject/{name}` | Отклонить (немедленное удаление) |
| GET | `/graph/stats` | Статистика графа |

### Compliance (KZ GDPR)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/compliance/status` | TTL-статистика биометрических данных |
| DELETE | `/compliance/erase/{person}` | Право быть забытым (ст. 20 Закона РК) |
| POST | `/compliance/run-cleanup` | Ручной запуск TTL-очистки |

### Analytics & Health
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/health/metrics` | Расширенные метрики (диапазон до 31 дня) |
| GET | `/analytics/*` | Аналитика по темам, эмоциям, паттернам |
| GET | `/audit/*` | Аудит лог integrity chain |

---

## Android (Kotlin / Jetpack Compose)

**Min SDK:** 26 | **Target SDK:** 34 | **AGP:** 8.2.2

### Экраны
| Экран | Назначение |
|-------|------------|
| `SplashScreen` | Инициализация, проверка подключения |
| `RecordingListScreen` | Список транскрипций дня |
| `DailySummaryScreen` | Дайджест (30 сек timeout) |
| `VoiceEnrollmentScreen` | Запись голосового профиля (60 сек timeout) |
| `AnalyticsScreen` | Аналитика паттернов и эмоций |

### Ключевые компоненты
- `BalanceWheelVisualizer` — GPU-accelerated визуализация 8 сфер жизни
- `ParticleFieldVisualizer` — 300 частиц с физикой (60 FPS, +2% battery/час)
- `AudioSpectrumAnalyzer` — FFT анализ (8 частотных полос)
- `PendingUpload` + `UploadWorker` — offline queue (Room DB → retry при появлении сети)

### Сетевой стек
- WebSocket: binary audio streaming (VAD сегменты 3 сек)
- HTTP: Retrofit + OkHttp (30 сек timeout для digest, 60 сек для enrollment)
- Network security config: prod HTTPS/WSS, debug HTTP/WS

---

## База данных (SQLite + SQLCipher AES-256)

**Файл:** `src/storage/reflexio.db` | **WAL mode** | **Шифрование:** AES-256-CBC

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
| `schema_migrations` | История применённых миграций (0001–0013) |

### Миграции
- 0001–0009: PostgreSQL-совместимые (legacy)
- 0010–0013: SQLite-специфичные (digest_cache, acoustic, vec, missing_tables)

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
enrichment_version: str     # "2.1.0" — версия логики
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
| **Cache** | Redis 7 alpine (rate limiting counters) |
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
| **Rate Limiting** | slowapi + Redis: 10/мин ingest, 30/мин ASR, 200/мин health |
| **Storage** | SQLCipher AES-256-CBC + file-based key fallback |
| **Input** | SAFE middleware (25 MB limit, audit mode), input_guard middleware |
| **PII** | Privacy pipeline audit mode; SQLCIPHER_KEY из env, не в коде |
| **Circuit Breakers** | 5 failures → 60s pause для каждого LLM провайдера |
| **Compliance** | KZ GDPR: TTL cleanup 03:00, DELETE /compliance/erase/{person} |
| **Integrity** | SHA-256 hash chain для каждой транскрипции |
| **API Keys** | Только в .env, никогда в коде; ротируются (score 10/10) |

**Security Score: 10/10** (достигнут 2026-03-03)

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

### KùzuDB (multi-hop граф)
Встроенный граф-движок — shortest path, clusters, соседи за N hops.
```bash
# 1. Раскомментировать в requirements.txt: kuzu>=0.7.0
# 2. docker compose up -d --build
# 3. engine.sync_from_sqlite(db_path) после каждого approve_profile()
```

---

## Дорожная карта

### v1.1 (следующий спринт)
- [ ] Beta testing: 500 пользователей (referral + Product Hunt)
- [ ] Graph API: `/graph/paths`, `/graph/clusters` (нужен KùzuDB)
- [ ] Активация pyannote.audio на проде

### v1.2
- [ ] English language support
- [ ] Slack integration (weekly digest в канал)
- [ ] Team edition (общий граф команды)

### v2.0
- [ ] Real-time insights (не дайджест раз в день, а push-уведомления)
- [ ] On-device ASR (Whisper.cpp Android, приватность)
- [ ] Локальный LLM (Ollama на RTX 5070 Ti)

---

## Стек технологий

**Backend:** Python 3.11, FastAPI 0.110+, SQLite/SQLCipher, Redis, APScheduler
**ML:** faster-whisper (Whisper medium), librosa (acoustic), resemblyzer (GE2E), sentence-transformers, sqlite-vec
**LLM:** Google Gemini Flash / Anthropic Claude Haiku / OpenAI GPT-4o-mini (cascade)
**Android:** Kotlin, Jetpack Compose, Room, WorkManager, OkHttp
**Infra:** Docker multi-stage, Caddy, Hetzner VPS
**Quality:** ruff, structlog, pydantic v2, pytest (595 tests)
