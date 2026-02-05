# Decisions (Memory Bank)

**Источник:** интеграция Golos в 24 na 7.

## ADR: Размещение модулей Golos

- Модули захвата звука и транскрипции из Golos размещены в `src/reflexio/` (audio, transcription).
- Имена пакетов: `reflexio.audio`, `reflexio.transcription` (не golos).

## ADR: Точка входа

- `src.reflexio.main:app` реэкспортирует `app` из `src.api.main` для совместимости с задачей запуска без дублирования логики.

## ADR: Memory Bank

- Создана отдельная папка `.cursor/memory_bank/` для практик из Golos; `.cursor/memory/` не изменялась.
