# Active Context — Reflexio 24/7

## Последнее обновление
2026-03-08 (Session 3: Cascade JSON Fix + pyannote Activation)

## Текущая фаза
**v0.4.5 Cascade Resilience + Speaker Diarization**

## Сессия 2026-03-08 (часть 3): Cascade JSON Fix + pyannote

### Cascade JSON Validation Fix (`c9584cd`):
- **Баг:** Gemini 2.5 Flash возвращал обрезанный JSON → enrichment пустой
- **Фикс:** `validate_fn` в CascadeLLMClient проверяет JSON parsability
- При невалидном JSON → cascade пробует Haiku → enrichment полный
- Живой тест: `cascade_provider_validation_failed` (Gemini) → Haiku подхватил

### pyannote.audio Activation (`541deb9`, `c4b515d`):
- Раскомментирован в requirements.txt, HF_TOKEN уже в .env
- Dockerfile: torch CPU-only (~300MB вместо 5GB CUDA)
- Docker полный сброс (containerd corruption → rm -rf + restart)
- **Образ:** 4.14GB (было 17.5GB), 22GB свободно
- pyannote 4.0.4 + torch 2.10.0+cpu установлены

### Все коммиты дня (pushed to main):
- `c9584cd` — fix: cascade fallback on invalid JSON from Gemini
- `541deb9` — feat: enable pyannote.audio for speaker diarization
- `c4b515d` — fix: Dockerfile CPU-only torch
- `803d3cd` — fix(android): wire HistoryScreen into UI
- `d997d78` — feat(android): CommitmentsScreen
- `cc439b8` — UI theme merge (Codex)
- `e64d9a9` — feat: CCBM context optimizer
- `5f463ec` — fix: speaker verification threshold 0.60→0.75
- `06c9f4c` — fix(android): disconnect WebSocket in onDestroy
- `8cd6f81` — feat: commitment extraction
- `5d97d23` — fix: 1 uvicorn worker (OOM)
- `6158fa7` — fix: speech filter thresholds
- `36edf7d` — feat: async ingest pipeline + pipeline status UI

## Продакшн статус
- **API:** https://reflexio247.duckdns.org/health → ok
- **VPS:** CX33, 22GB свободно, Docker образ 4.14GB
- **pyannote:** 4.0.4 installed (дариазция готова, не интегрирована в pipeline)
- **Cascade:** Gemini→Haiku→GPT-4o-mini с JSON validation
- **APK:** CommitmentsScreen + HistoryScreen (не нужна пересборка)

## СЛЕДУЮЩАЯ СЕССИЯ — Бэклог
- Интеграция diarize.py в audio_processing.py pipeline
- Мульти-профили голосов (enrollment семьи)
- Классификация м/ж по pitch
- Intent fallback (LLM classifier для /ask)
- CCBM установка на VPS
- Whisper watchdog
