# Active Context

**Обновлено:** интеграция Golos → 24 na 7

## Текущий фокус

- Пакет `src/reflexio/`: захват аудио (AudioRecorder, VAD, buffer) и транскрипция (WhisperEngine).
- Точка входа: `uvicorn src.reflexio.main:app --reload` (реэкспорт из src.api.main).
- Memory Bank и правила дополнены практиками из Golos.

## Ключевые пути

- Аудио: `src/reflexio/audio/` (capture, vad, buffer).
- Транскрипция: `src/reflexio/transcription/` (WhisperEngine).
- API: `src/api/main.py`.
