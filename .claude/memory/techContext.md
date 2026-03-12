# Tech Context — Reflexio 24/7

## Окружение
- Dev OS: Windows 11 Pro
- Python: 3.11+ (conda)
- Workspace: `D:\24 na 7`
- Git remote: `https://github.com/sergeeey/24-na-7.git`
- Prod target: `root@46.225.211.115`, app path `/opt/reflexio`

## Backend стек
- FastAPI + uvicorn
- slowapi для rate limiting
- SQLite / SQLCipher через `src/storage/db.py`
- Redis в production compose для rate limiting storage
- APScheduler для фоновых задач
- faster-whisper / audio pipeline
- async ingest worker + async enrichment worker
- LLM cascade: Google / Anthropic / OpenAI

## Runtime архитектура
- `src/core/bootstrap.py` управляет lifecycle, APScheduler, ingest worker, enrichment worker
- `src/core/audio_processing.py` содержит unified audio pipeline и sync/async enrichment entrypoints
- `src/api/routers/ingest.py` экспонирует status/trends/reprocess для ingest pipeline
- `src/memory/truth.py` и `src/api/routers/admin.py` покрывают truth-layer recovery (`reclassify`, `recheck`)

## Operational детали
- ingest watchdog:
  - `received/pending` > 30 мин → `retryable_error`
  - `asr_pending` > 45 мин → `retryable_error`
- ingest recovery:
  - bounded resume backlog из SQLite в in-memory worker
  - missing audio → `quarantined`
- enrichment queue:
  - 2 worker'а
  - bounded retry до 2 повторов
  - после лимита: запись остаётся `transcribed` с `enrichment_failed`
- backups:
  - APScheduler cron `04:00`
  - snapshots в `STORAGE_PATH/backups`
  - retention 7 дней
- SLO alerting:
  - hook на Telegram sender
  - отправка только при `slo_state != healthy` дольше 30 минут
  - требует `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`

## Prod compose
- файл: `docker-compose.prod.yml`
- `api` healthcheck:
  - `curl -f http://localhost:8000/health`
  - `interval: 30s`
  - `timeout: 10s`
  - `retries: 3`
- код в prod подхватывается через volume `./src:/app/src`

## Известные ограничения
- полная калибровка truth layer и dogfooding требуют живых данных и времени наблюдения
- deploy/push/merge возможны только при валидном git auth и SSH доступе
- часть ветки уже содержит WIP changes; перед merge нужен аккуратный commit discipline
