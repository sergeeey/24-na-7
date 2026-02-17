---
name: Reflexio Patterns
trigger: on_pattern_match
version: 1.0
---

# Reflexio Development Patterns

## Архитектурные паттерны

### Модульная структура
- Каждый модуль ≤500 строк кода
- Чёткие границы между модулями
- Использование Result-паттерна для обработки ошибок

### Логирование
- Всегда использовать structlog
- Каждый этап пайплайна пишет event-лог
- Уровни: info/debug/warning/error + traceID

### Валидация
- Все входы/выходы через Pydantic модели
- FastAPI body-валидация
- Шаблоны данных: Fact, Insight, Task

### Обработка ошибок
- Использовать Result-паттерн (`Result.ok`, `Result.err`)
- Кастомные исключения: `ReflexioError`, `IngestError`, `ASRError`
- Логировать все ошибки с контекстом

## Workflow паттерны

1. **Edge** — слушаем и режем речь (webrtcvad)
2. **ASR** — `faster-whisper` → transcript (text + conf)
3. **Analyze** — pipeline Ф→С→Э→О→К (Факт → Смысл → Эмоция → Ответ → Контекст)
4. **Digest** — `digests/YYYY-MM-DD.md`
5. **Bot** — отправка в Telegram

## Тестирование

- pytest + coverage ≥85%
- happy / edge / error tests
- Smoke-тесты и health-check endpoints













