# Active Context — Reflexio 24/7

## Последнее обновление
2026-02-25 15:00

## Текущая фаза
**Pipeline production-ready + repo clean + security hardened**

## Сессия 2026-02-25 (вторая половина дня)

### Task B: Чистка репо ✅ (коммит `01365cb`)
- Удалено 50+ AI-bloat .md файлов из корня (OSINT_, W1D1_, SERP_, LEVEL5_, etc.)
- Удалено 40+ .md файлов из docs/ (INTEGRATION_SPRINT_*, AUDIT_*, etc.)
- Оставлено 11 полезных docs/: DEPLOYMENT, QUICKSTART, SECURITY, RUNBOOKS, spec, risks, steps, QUICK_COMMANDS, ENV_SETUP_INSTRUCTIONS, FILTERS, DIGEST
- risks.md, spec.md, steps.md → перенесены в docs/
- .gitignore обновлён: android/.gradle/, android/nul, .claude/worktrees/
- core_memory.json скопирован из .cursor/memory → .claude/memory/

### Task C: Боевой digest ✅
- Проверен через Docker API: digest за 2026-02-24 генерирует правильный русский саммари
- CoD работает: "Марат обсудили бюджет Q2, сократить расходы 15%, позвонить в банк"
- Tasks извлечены: "Подготовить таблицу к пятнице", "Позвонить в банк"
- ⚠️ Confidence: 0.00 — известный баг (critic оценивает против зашумлённого текста)
- Локально без API key: саммари пустое (expected) → Docker работает корректно

### Task A: Unify dual pipeline ✅ (коммит `9f3dee1`)
- Explorer подтвердил: core pipeline УЖЕ унифицирован в `process_audio_bytes()`
- Нет дублирования бизнес-логики между ingest.py и websocket.py
- SAFEChecker → singleton (было: новый экземпляр per request) в `safe_middleware.py`
- WebSocket: добавлен SAFE size check (25MB limit) для binary и base64 путей
- Ошибка при добавлении: `check_file_size(Path)` не принимает int → фикс через `.MAX_FILE_SIZE_BYTES`

## Все коммиты сессии (хронологически)
- `2b33f3f` — fix(asr): switch to local Whisper, fix recursion and OpenAI model name
- `035ab47` — fix(digest): filter noise transcriptions and enforce Russian in LLM output
- `e07a617` — feat(audio): P0-P3 noise filter, music rejection, auto-delete WAV
- `324c7b1` — fix(asr): force Russian language and upgrade to medium model
- `709bb3b` — feat: privacy pipeline, integrity chain, semantic memory (Codex)
- `fee67d8` — test: fix 3 remaining failures + add balance/persongraph tests (559 pass)
- `01365cb` — chore: remove 90+ AI-bloat .md files, organize docs/ structure
- `9f3dee1` — feat(pipeline): unify security - SAFE singleton + WebSocket size check

## Pipeline (текущий)
```
Pixel 9 Pro → VAD (3-сек сегменты) → WebSocket binary
  → P0: SpeechFilter (FFT, speech 300-3400Hz vs music >4kHz)
  → SAFE size check (25MB) ← NEW в WebSocket
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

## Статус тестов (9f3dee1)
- **559 passed, 26 skipped, 0 failed** (полный suite)

## Следующие шаги
1. Android: offline queue + retry logic (WorkManager)
2. Stage-2 memory: эмбеддинги + rerank для semantic retrieval
3. Confidence bug: critic должен оценивать против filtered text, не raw text
4. Push последних 2 коммитов (01365cb, 9f3dee1)

## Ключевые файлы
- API: `src/api/main.py`
- WebSocket: `src/api/routers/websocket.py` (P0+SAFE+P1+P2 фильтры)
- Ingest: `src/api/routers/ingest.py`
- Core pipeline: `src/core/audio_processing.py` (process_audio_bytes)
- ASR: `src/asr/transcribe.py`, `config/asr.yaml`
- Digest: `src/digest/generator.py` (noise filter + CoD)
- SAFE: `src/validation/safe/checks.py`, `src/api/middleware/safe_middleware.py`
- Config: `src/utils/config.py` (ASR_LANGUAGE, FILTER_MUSIC, PRIVACY_MODE)
- Privacy: `src/security/privacy_pipeline.py`
- Integrity: `src/storage/integrity.py`
- Memory: `src/memory/semantic_memory.py`

## Для восстановления контекста
Reflexio 24/7: `D:/24 na 7/`. Pipeline production-ready: Android → VAD → SpeechFilter → SAFE size check → Whisper medium (ru) → noise filter → privacy → SQLite + integrity → auto-delete WAV → enrichment (Claude Haiku) → semantic memory → CoD digest. Docker работает. 559 тестов зелёных. Репо очищен от 90+ AI-bloat файлов. Dual pipeline уже был унифицирован в process_audio_bytes() — добавили только SAFE singleton + WS size check.
