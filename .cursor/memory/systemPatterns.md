# System Patterns: Reflexio 24/7

## Архитектурный паттерн

Модульный монолит (Modulith).  

Единое приложение, разбитое на изолированные модули с чёткими границами.  

Позволяет масштабировать в микросервисы позже.

## Логирование

- `structlog` в JSON-режиме

- Каждый этап пайплайна (VAD → ASR → Analyze → Digest) пишет event-лог

- Уровни: info/debug/warning/error + traceID

## Ошибки

- Использовать Result-паттерн (`Result.ok`, `Result.err`)

- Любые исключения кастомные: `ReflexioError`, `IngestError`, `ASRError`

## Тестирование

- pytest + coverage ≥85%

- happy / edge / error tests

- Smoke-тесты и health-check endpoints

## Безопасность

- Zero-retention аудио

- Маскирование PII

- Нет телефонных звонков (юридические ограничения)

- `.env` → только через секрет-менеджер

## Валидация

- Все входы/выходы через Pydantic модели

- FastAPI body-валидация

- Шаблоны данных: Fact, Insight, Task

## Workflow

1. **Edge** — слушаем и режем речь (webrtcvad)

2. **ASR** — `faster-whisper` → transcript (text + conf)

3. **Analyze** — pipeline Ф→С→Э→О→К

4. **Digest** — `digests/YYYY-MM-DD.md`

5. **Bot** — отправка в Telegram

## CI/CD

- GitHub Actions

- Проверки: ruff, mypy, pytest, coverage, black

- Conventional commits

## Observability

- latency, throughput, error rate

- async jobs с логами длительности

