# Active Context — Reflexio 24/7

## Последнее обновление
2026-02-25 13:45

## Текущая фаза
**Pipeline production-ready: фильтрация шума, русская ASR, auto-cleanup, privacy/integrity**

## Что сделано за сессию 2026-02-25

### ASR исправления
- **OpenAI API ошибка:** `whisper-large-v3-turbo` (HuggingFace имя) → 404, 14 сек retry. Переключили на `provider: local`
- **Бесконечная рекурсия:** `LocalProvider → transcribe_audio → get_asr_provider → LocalProvider`. Fix: `_asr_provider = None` + `_asr_provider_initialized` flag
- **Язык:** `language=None` → Whisper угадывал `en`/`nn` для русской речи. Fix: `ASR_LANGUAGE=ru`
- **Модель:** `small` + `int8` + CPU не тянул русский. Fix: `ASR_MODEL_SIZE=medium`
- Результат: text_length 24-50, confidence 1.0, язык всегда `ru`

### Фильтрация мусора (10 000+ записей → 0)
- **P0: SpeechFilter** — FFT анализ спектра в WebSocket handler ДО Whisper. `FILTER_MUSIC=true`
- **P1: _is_meaningful_transcription()** — min 3 слова, не стоп-фразы, lang_prob > 0.4. Блокирует запись в БД
- **Digest фильтры** — `_is_meaningful()`, `_has_cyrillic()`, лимит 100 записей/4000 символов для LLM
- **LLM промпты** — "ВСЕГДА на русском", обрезка текста до 4000 chars

### Auto-cleanup WAV файлов
- **P2: Сервер** — `dest_path.unlink()` после persist (и при ошибке)
- **P3: Телефон** — `file.delete()` после успешного upload в `AudioRecordingService`
- Android WebSocket клиент обрабатывает `"filtered"` ответ

### Рефакторинг websocket.py
- Вынесен `_process_audio_segment()` — убрана 60-строчная дупликация binary/base64 путей

### Codex: Privacy + Integrity + Semantic Memory
- **Privacy pipeline** (`src/security/privacy_pipeline.py`) — strict/mask/audit PII detection
- **Integrity chain** (`src/storage/integrity.py`) — SHA-256 hash chain для audit trail
- **Semantic memory** (`src/memory/semantic_memory.py`) — консолидация транскрипций в memory nodes
- **API:** `/memory/search`, `/audit/trail`
- **Feature flags:** PRIVACY_MODE, MEMORY_ENABLED, RETRIEVAL_ENABLED, INTEGRITY_CHAIN_ENABLED
- **Security hardening:** SAFE checker static import, WAV magic bytes, path leak fix
- **Migration:** 0008_semantic_memory_integrity.sql
- **Tests:** 10 passed

## Коммиты сессии
- `2b33f3f` — fix(asr): switch to local Whisper, fix recursion and OpenAI model name
- `035ab47` — fix(digest): filter noise transcriptions and enforce Russian in LLM output
- `e07a617` — feat(audio): P0-P3 noise filter, music rejection, auto-delete WAV
- `324c7b1` — fix(asr): force Russian language and upgrade to medium model
- `709bb3b` — feat: privacy pipeline, integrity chain, semantic memory (Codex)
- `fee67d8` — test: fix 3 remaining failures + add balance/persongraph tests (559 pass)

Первые 5 запушены. fee67d8 — локально.

## Pipeline (текущий)
```
Pixel 9 Pro → VAD (3-сек сегменты) → WebSocket binary
  → P0: SpeechFilter (FFT, speech 300-3400Hz vs music >4kHz)
  → Whisper medium (language=ru, CPU int8)
  → P1: _is_meaningful_transcription (min 3 words, no noise phrases)
  → Privacy pipeline (audit mode)
  → SQLite persist + integrity chain
  → P2: WAV удалён на сервере
  → "transcription" + delete_audio:true → P3: WAV удалён на телефоне
  → Enrichment (Claude Haiku) → topics, emotions, tasks
  → Semantic memory consolidation
  → Digest: CoD summarization + Critic validation
```

## Docker
- Контейнер `reflexio-api` работает, health OK
- Volume mounts: `./src:/app/src` (dev mode), `./config:/app/config`
- Env: `FILTER_MUSIC=true`, `ASR_MODEL_SIZE=medium`, `ASR_LANGUAGE=ru`

## Статус тестов (fee67d8)
- **559 passed, 26 skipped, 0 failed** (полный suite)
- Ключевые фиксы: WAV signature bytes, pydantic-settings override, ASR state flags
- Новые тесты: balance/storage (17) + persongraph/service (18) = 35 тестов

## Следующие шаги
1. Протестировать дайджест за сегодня (есть реальные русские записи)
2. Чистка: 54 .md в корне, `android/.gradle/` в .gitignore
3. Android: offline queue, retry logic
4. Stage-2 memory: эмбеддинги + rerank для retrieval
5. SAFE checker: создать `src/validation/` модуль (сейчас warning при каждом запросе)

## Ключевые файлы
- API: `src/api/main.py`
- WebSocket: `src/api/routers/websocket.py` (P0+P1+P2 фильтры)
- ASR: `src/asr/transcribe.py`, `config/asr.yaml`
- Digest: `src/digest/generator.py` (noise filter + CoD)
- Config: `src/utils/config.py` (ASR_LANGUAGE, FILTER_MUSIC, PRIVACY_MODE)
- Privacy: `src/security/privacy_pipeline.py`
- Integrity: `src/storage/integrity.py`
- Memory: `src/memory/semantic_memory.py`
- Android WS: `android/.../IngestWebSocketClient.kt`
- Android Service: `android/.../AudioRecordingService.kt`

## Для восстановления контекста
Reflexio 24/7: `D:/24 na 7/`. Pipeline production-ready: Android → VAD → SpeechFilter → Whisper medium (ru) → noise filter → privacy → SQLite + integrity → auto-delete WAV → enrichment (Claude Haiku) → semantic memory. 5 коммитов запушены (709bb3b). Docker работает с volume mounts. Шум полностью отфильтрован (10K+ мусорных записей → 0). Русская речь распознаётся (confidence 1.0).
