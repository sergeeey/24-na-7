# Active Context — Reflexio 24/7

## Последнее обновление
2026-03-12

## Текущая фаза
**v0.5.2-beta branch gate / pre-production trusted episodic memory**

## Что подтверждено локально
- Ветка: `codex/episodic-memory-pass`
- Полный regression suite зелёный: `669 passed, 26 skipped`
- Admin recovery endpoints, truth layer, ingest watchdog/recovery и episodic pipeline проходят локальные тесты
- E2E `test_full_pipeline` снова зелёный после замены пустой WAV фикстуры на короткий PCM speech-like sample

## Что уже реализовано в коде ветки
- watchdog для `received` и `asr_pending` с переводом в `retryable_error`
- recovery retry backlog для ingest через `recover_retryable_ingest_tasks()`
- расширенные `/ingest/pipeline-status` и `/ingest/pipeline-trends` с `ingest_health`, stale/recovery counters и latency
- reprocess stale ingest для зависших `received/asr_pending`
- bounded retry для async enrichment queue: до 2 повторов, затем graceful degradation в `transcribed`
- SQLite backup automation hook в APScheduler (`04:00`, retention 7 дней)
- SLO Telegram alert hook через existing Telegram sender при unhealthy > 30 минут
- prod healthcheck timeout приведён к `10s`

## Что осталось внешним
- merge ветки в `main`
- push/tag
- deploy на VPS `root@46.225.211.115`
- post-deploy smoke (`/health`, `/ingest/pipeline-status`, `/ingest/pipeline-trends`, WebSocket ingest, `/digest/today`)
- недельные фазы calibration / operational maturity / dogfooding

## Риски на текущий момент
- worktree грязный: есть незакоммиченные WIP-изменения в ingest/bootstrap/worker/test files
- продовые операции зависят от наличия git/SSH/docker доступа из текущей сессии
- Telegram alerting активируется только если на среде заданы `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`
