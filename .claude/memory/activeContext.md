# Active Context — Reflexio 24/7

## Последнее обновление
2026-02-25 23:45

## Текущая фаза
**Android Balance Wheel + чистая база данных — коммит `6d8e088`**

## Сессия 2026-02-25 (вечер — продолжение 3)

### Все исправления из security audit (кроме C1 ключей) ✅ (коммит `34d6c51`)

#### Что сделано:

**H5 — убрали importlib RCE вектор (2 места):**
- `safe_middleware.py`: удалили `importlib.util.spec_from_file_location()` из `.cursor/` — потенциальный RCE. Статический импорт остался.
- `digest/generator.py`: убрали CoVe importlib блок в `generate_json()` — та же проблема.

**H3 — Redis для rate limiting:**
- `docker-compose.yml`: включили `redis:7-alpine` с healthcheck, AOF persistence (`--appendonly yes`), volume `redis-data`
- api service: `RATE_LIMIT_STORAGE=redis`, `REDIS_URL=redis://redis:6379/0`, `depends_on: redis`
- Код `rate_limiter.py` уже поддерживал Redis через `REDIS_URL` env var

**Confidence bug — critic/deepconf:**
- `digest/generator.py` `generate_markdown()`: `confidence_threshold` 0.85→0.70, `auto_refine` True→False
- Было: порог 0.85 с эвристиками → почти всегда < 0.85 → лишний LLM вызов каждый раз
- Стало: 0.70 (как `get_daily_digest_json`), `auto_refine=False` — экономия токенов

**Android WiFi fix:**
- `build.gradle.kts`: добавили `import java.util.Properties` + чтение из `local.properties`
- `SERVER_WS_URL_DEVICE` = `localProps.getProperty("SERVER_WS_URL_DEVICE", "ws://localhost:8000")`
- USB+adb: default `ws://localhost:8000`, WiFi: добавить в `local.properties` (gitignored)

**Scope creep cleanup:**
- `src/osint/` (15 файлов) → `_archive/osint/` (OSINT pipeline — не используется)
- `src/billing/` (4 файла) → `_archive/billing/` (stripe, freemium — преждевременно)
- `src/llm/prompts/manager.py`: убрали `from src.osint.contextor import build_rctf_prompt` + PromptType.OSINT_RCTF

**resemblyzer / Dockerfile:**
- `Dockerfile.api`: добавили комментарий что includes resemblyzer и redis
- requirements.txt уже содержал `resemblyzer>=0.1.1` — достаточно пересобрать образ

---

## ОТКРЫТЫЕ действия (требуют рук):

**Docker** — ✅ ЗАПУЩЕН (reflexio-api + reflexio-redis, оба healthy)


**C1 (CRITICAL) ⚠️ СРОЧНО — ротировать API ключи**
- OpenAI: https://platform.openai.com/api-keys
- Anthropic: https://console.anthropic.com/settings/keys

**Docker rebuild** (обязательно после коммита):
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
# После rebuild: resemblyzer и redis оба работают
```

**Speaker enrollment** (после docker rebuild):
```bash
# 1. Записать 3+ образца своего голоса (WAV, 16kHz, 3-10 сек каждый)
curl -X POST http://localhost:8000/voice/enroll \
     -H "Authorization: Bearer $API_KEY" \
     -F "files=@sample1.wav" \
     -F "files=@sample2.wav" \
     -F "files=@sample3.wav"

# 2. Включить в .env:
SPEAKER_VERIFICATION_ENABLED=true
SPEAKER_SIMILARITY_THRESHOLD=0.75
```

**Android WiFi** (если нужен WiFi без кабеля):
```
# Добавить в android/local.properties (gitignored):
SERVER_WS_URL_DEVICE=ws://192.168.1.XXX:8000
```

---

## Сессия 2026-02-25 (вечер — продолжение 3): Docker запуск

### Проблемы и фиксы:

**Порт 6379 конфликт:**
- `terag-redis` от другого проекта занял порт 6379
- Fix: убрали `ports: "6379:6379"` из redis сервиса в docker-compose.yml
- Redis внутри reflexio-net доступен api по имени `redis:6379` без host binding
- Бонус: Redis не доступен с хоста снаружи (безопаснее)

**SyntaxError в audio_processing.py:**
- Строка 432: f-string с `""` внутри `f"..."` — Python 3.11 не поддерживает
- (Python 3.12 пофиксил, но у нас 3.11-slim в Docker)
- Fix: `""` → `''` внутри f-string expression

**Результат:** оба контейнера healthy, `rate_limiter_using_redis` подтверждён в логах

---

## Сессия 2026-02-25 (финал): Balance Wheel + чистый старт

### Что сделано:
- **Сервер**: `reflexio.db` удалена (14 838 записей) → `docker restart reflexio-api` → чистая БД
- **Android**: `adb shell pm clear com.reflexio.app` → Room DB очищена
- **`BalanceWheelVisualizer.kt`** (новый): радар 8 доменов, 3D tilt + медленное вращение при записи
  - Fetches `/balance/wheel?date=today` на каждый toggle записи
  - Default scores 5f (нейтральное колесо) при пустой БД
- **`MainActivity.kt`**: убраны RecordingListScreen + ParticleFieldVisualizer + AudioSpectrumAnalyzer
  - HomeScreen: WelcomeBlock → BalanceWheelVisualizer (weight=1f) → FAB
  - RecordingApp: убран recordingDao параметр
- **Коммит `6d8e088`** feat(android): replace recording list with Balance Wheel visualizer

---

## Все коммиты (хронологически)
- `2b33f3f` — fix(asr): switch to local Whisper, fix recursion and OpenAI model name
- `035ab47` — fix(digest): filter noise transcriptions and enforce Russian in LLM output
- `e07a617` — feat(audio): P0-P3 noise filter, music rejection, auto-delete WAV
- `324c7b1` — fix(asr): force Russian language and upgrade to medium model
- `709bb3b` — feat: privacy pipeline, integrity chain, semantic memory (Codex)
- `fee67d8` — test: fix 3 remaining failures + add balance/persongraph tests (559 pass)
- `01365cb` — chore: remove 90+ AI-bloat .md files, organize docs/ structure
- `9f3dee1` — feat(pipeline): unify security - SAFE singleton + WebSocket size check
- `2a5e290` — fix(security): close 4 production blockers — auth, CORS, error leakage, KZ PII
- `3d3ab6b` — feat(speaker): add speaker verification module (resemblyzer GE2E)
- `34d6c51` — fix(security): H5 importlib RCE, H3 Redis, confidence bug, Android WiFi, scope cleanup
- `3b79a73` — fix(docker): remove redis host port conflict, fix f-string syntax in audio_processing.py
- `9b80e59` — feat(android): add voice enrollment screen + SampleRecorder
- `6d8e088` — feat(android): replace recording list with Balance Wheel visualizer

## Security Score
- Было: **6/10 BLOCK**
- После 2a5e290: **~8/10**
- После 34d6c51: **~9/10** (H5 RCE закрыт, H3 Redis включён, scope clean)
- До 10/10: ротировать C1 ключи (ручное действие)

## Статус тестов (34d6c51)
- **587 passed, 26 skipped, 0 failed**

## Pipeline (текущий)
```
Pixel 9 Pro → VAD (3-сек сегменты) → WebSocket binary
  → P0: SpeechFilter (FFT, speech 300-3400Hz vs music >4kHz)
  → SAFE size check (25MB)
  → P4: SpeakerVerification (disabled by default; resemblyzer GE2E ~50ms)
  → Whisper medium (language=ru, CPU int8)
  → P1: _is_meaningful_transcription (min 3 words, no noise phrases)
  → Privacy pipeline (audit mode)
  → SQLite persist + integrity chain
  → P2: WAV удалён на сервере
  → "transcription" + delete_audio:true → P3: WAV удалён на телефоне
  → Enrichment (Claude Haiku) → topics, emotions, tasks
  → Semantic memory consolidation
  → Digest: CoD (CoD confidence_threshold=0.70, auto_refine=False) + Critic
```

## Docker (после rebuild)
- `reflexio-api` + `reflexio-redis` (два контейнера)
- Redis: AOF persistence, healthcheck, volume `redis-data`
- Rate limiting: `redis://redis:6379/0` (persistent, DDoS-safe)
- Команда: `docker compose build --no-cache && docker compose up -d`

## Сессия 2026-02-25 (Social Graph Sprint)

### Коммит `9548a21` — feat(social-graph)

**Что реализовано:**

**`src/persongraph/anchor.py`** (новый)
- `NameAnchorExtractor` — ищет звательные обращения ("Максим,") перед сменой спикера
- 3 regex паттерна: trailing comma, vocative clause, "Эй, имя"
- `_MAX_GAP_SEC = 3.0` — максимальный зазор между репликами
- Минимальная длина сегмента-кандидата 1.5 сек (шум фильтруется)

**`src/persongraph/accumulator.py`** (новый)
- `VoiceProfileAccumulator` — накапливает GE2E d-vectors по якорям
- Порог: `MIN_SAMPLES=10`, `MIN_CONFIDENCE=0.85` (из GE2E paper)
- Профиль не создаётся автоматически → `pending_approval` → уведомление → пользователь подтверждает
- `approve_profile()`: взвешенное среднее d-vectors + нормализация на единичную сферу
- `reject_profile()`: немедленное удаление всех сэмплов

**`src/persongraph/compliance.py`** (новый)
- `BiometricComplianceManager` — KZ GDPR TTL cleanup
- TTL: неидентифицированные 7 дней, pending 30 дней, профили 365 дней
- `delete_person_data()` — полное удаление (ст. 20 ЗРК)
- `get_compliance_status()` — для GET /compliance/status

**`src/storage/migrations/0009_social_graph.sql`** (новый)
- Таблицы: `persons`, `person_voice_samples`, `person_voice_profiles`, `person_interactions`
- ВАЖНО: `person_voice_profiles` (не `voice_profiles`) — избегаем коллизии с `speaker/storage.py`
- TTL index на `(person_name, status, created_at)` для быстрой очистки

**`src/storage/db.py`** — ALLOWED_TABLES пополнен новыми таблицами

**Тесты:** 587 passed, 26 skipped, 0 failed ✅

---

## Следующие шаги
1. **СРОЧНО**: Ротировать OpenAI и Anthropic ключи (C1) — единственный блокер до 10/10
2. **Speaker enrollment**: вкладка "Голос" в приложении → записать 3 образца → включить `SPEAKER_VERIFICATION_ENABLED=true`
3. **Sprint 2 (следующая сессия)**:
   - Pyannote.audio интеграция (`src/asr/diarize.py`) — нужен HF_TOKEN
   - Social Graph API роутер (`src/api/routers/graph.py`)
   - Compliance API роутер (`src/api/routers/compliance.py`)
   - APScheduler для ежедневного запуска compliance cleanup
4. **Sprint 3**: KùzuDB engine для multi-hop запросов
5. **Stage-2 memory**: эмбеддинги + rerank (backlog)

## Ключевые файлы (изменённые в 34d6c51)
- `src/api/middleware/safe_middleware.py` — H5 fix
- `src/digest/generator.py` — H5 CoVe + confidence bug fix
- `docker-compose.yml` — Redis enabled
- `Dockerfile.api` — комментарий о resemblyzer
- `android/app/build.gradle.kts` — local.properties override
- `src/llm/prompts/manager.py` — убран osint импорт
- `_archive/` — osint + billing заархивированы

## Для восстановления контекста
Reflexio 24/7: `D:/24 na 7/`. Security Score ~9/10. Коммит `34d6c51`: H5 importlib RCE закрыт в двух местах, H3 Redis включён (AOF persistence), confidence bug исправлен (auto_refine=False, threshold 0.70), Android WiFi через local.properties, osint+billing в _archive. 587 тестов зелёных. СРОЧНО: ротировать ключи (C1)! Затем: docker compose build --no-cache + speaker enrollment.
