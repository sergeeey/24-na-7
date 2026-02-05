# CLAUDE — Инструкции для AI-ассистента

**Проект:** 24 na 7 (Reflexio)  
**Обновлено:** интеграция Golos — захват звука и транскрипция в пакете `reflexio`.

## Контекст проекта

- **24 na 7** — AI-Native система записи речи, транскрипции и дайджестов. После интеграции Golos добавлен пакет `src/reflexio/` с модулями захвата аудио и транскрипции.
- **Точки входа:** `uvicorn src.api.main:app --reload` (основное API), `uvicorn src.reflexio.main:app --reload` (то же приложение, реэкспорт для совместимости с Golos).

## Пакет reflexio

- **audio:** `AudioRecorder`, `VADetector`, `AudioBuffer` — захват с микрофона, VAD, буфер кадров, запись WAV.
- **transcription:** `WhisperEngine` — обёртка над ASR (faster-whisper / провайдеры 24 na 7).
- Импорты: `from reflexio.audio import AudioRecorder`; `from reflexio.transcription import WhisperEngine`. Для работы из корня проекта нужен `PYTHONPATH=src` или установка пакета (`pip install -e .` с настроенным src-layout).

## Правила

- Не менять корневой `requirements.txt` и версии зависимостей без явной необходимости.
- Не менять конфиги 24 na 7 (docker-compose, .env.example и т.д.) в рамках задач по reflexio.
- В коде reflexio сохранять комментарии на русском и использовать относительные пути.
- При объединении с дополнительным содержимым из Golos — дополнять этот файл, не заменять целиком.

## Память и правила Cursor

- `.cursor/memory/` — контекст 24 na 7.
- `.cursor/memory_bank/` — практики из Golos (activeContext, projectbrief, systemPatterns, decisions, progress).
- `.cursor/rules/` — base_rules.yaml, reflexio-patterns.md и файлы *.mdc (00-general, 05-security, 20-testing) из интеграции Golos.

---
*При наличии оригинального CLAUDE.md из Golos его содержимое можно объединить с этим файлом (добавить секции выше или ниже).*
