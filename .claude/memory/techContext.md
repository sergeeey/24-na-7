# Tech Context — Reflexio 24/7

## Окружение разработки
- OS: Windows 11 Pro (build 26200)
- Python: 3.11+ (conda)
- GPU: RTX 5070 Ti (16 GB VRAM) — хватает на Whisper small/medium
- RAM: 96 GB
- IDE: Claude Code (основной), Cursor (legacy)

## Стек
- **FastAPI** — веб-фреймворк, uvicorn
- **faster-whisper** — ASR (small int8 по умолчанию)
- **webrtcvad** — Voice Activity Detection
- **sounddevice** — захват аудио с микрофона
- **librosa** — анализ спектра (фильтрация музыки)
- **structlog** — логирование
- **pydantic / pydantic-settings** — валидация, конфигурация
- **slowapi** — rate limiting
- **SQLite** — MVP storage (→ Supabase в проде)
- **OpenAI / Anthropic API** — LLM для enrichment

## Зависимости (потенциальные проблемы)
- `sounddevice` — требует PortAudio (может не быть на Windows без доп установки)
- `webrtcvad` — C-extension, может быть проблема при pip install на Windows
- `faster-whisper` — требует ctranslate2, ~500 MB модель при первом запуске
- `redis` — в requirements, но для MVP не нужен (rate limiting в memory)
- `hvac` — HashiCorp Vault клиент, для MVP не нужен
- Letta SDK — используется в memory/core_memory.py, может не быть установлен

## База данных (SQLite MVP)
Таблицы (schema.sql):
- `ingest_queue` — загруженные аудиофайлы (id, filename, path, size, status)
- `transcriptions` — транскрипции (text, language, duration, segments JSON)
- `facts` — извлечённые факты (fact_text, timestamp, confidence)
- `digests` — метаданные дайджестов (date, summary, facts_count)
- `recording_analyses` — анализы записей (summary, emotions, actions, topics)

## Конфигурация (.env)
- `LLM_PROVIDER` — openai | anthropic
- `DB_BACKEND` — sqlite | supabase
- `ASR_MODEL_SIZE` — tiny/small/medium/large
- `FILTER_MUSIC` — фильтр музыки/шума
- `SAFE_MODE` — audit | strict | disabled
- `VAULT_ENABLED` — false для MVP

## API Endpoints (8 роутеров)
- `/health` — health check
- `/ingest/audio` — POST загрузка аудио
- `/asr/transcribe` — POST транскрипция
- `/digest/today` — GET дайджест за сегодня
- `/digest/{date}` — GET дайджест за дату
- `/metrics` — метрики системы
- `/search/phrases` — поиск по фразам
- `/voice/intent` — распознавание намерений
- `/ws/ingest` — WebSocket для потокового аудио
