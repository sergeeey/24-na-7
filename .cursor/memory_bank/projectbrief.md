# Project Brief (Memory Bank)

**Источник:** интеграция лучших практик из Golos в 24 na 7.

## Миссия

Reflexio 24/7 — AI-Native система пассивной записи речи, транскрипции и анализа. Дополнена модулями захвата звука из проекта Golos в пакете `reflexio` (audio, transcription).

## Цели

- Единый проект 24 na 7 с функционалом Golos внутри.
- Импорты: `from reflexio.audio import AudioRecorder`, `from reflexio.transcription import WhisperEngine`.
- Запуск: `uvicorn src.reflexio.main:app --reload`.

## Архитектура

- `src/reflexio/audio/` — захват с VAD, буфер, запись WAV.
- `src/reflexio/transcription/` — WhisperEngine поверх ASR 24 na 7.
- `src/api/main.py` — основное FastAPI-приложение; `src.reflexio.main` реэкспортирует его.
