# Active Context — Reflexio 24/7

## Последнее обновление
2026-02-24

## Текущая фаза
**Настройка рабочего окружения → Проверка запуска core pipeline**

## Что сделано за сессию 2026-02-24

### Оценка состояния проекта
- Проект создан AI-агентами (Cursor + auto-claude), 13 коммитов
- 104 .py файла, ~16K строк в src/
- 54 .md файла в корне (bloat)
- Никогда не тестировался end-to-end
- Scope creep: 15 модулей, из которых ядро — 5 (edge, asr, digest, summarizer, storage)

### Переосмысление видения
- Было: "умный диктофон + дайджест дня"
- Стало: **"цифровая память всей жизни"**
- Вдохновение: модель Centaur (structured events, паттерны, предсказания)

### Настройка окружения
- Переписан CLAUDE.md (v2.0 — новое видение, архитектура, правила)
- Создана `.claude/memory/` (activeContext, techContext, decisions)
- Обновлены глобальные goals.md

## Что починено за сессию
- **Pipeline разрыв:** ingest и asr не писали в SQLite → добавлена запись в оба endpoint
- **policies.yaml:** битый YAML (экранирование `'` в regex) → починен
- **providers.py:** галлюцинированные модели (gpt-5-mini, claude-4-5) → исправлены на актуальные
- **providers.py:** баг в error handler Anthropic → починен (KeyError)
- **.env:** переключен на sqlite, LLM=anthropic (claude-3-haiku), SAFE=audit
- **metrics таблица:** создана в SQLite (health monitor больше не ругается)
- **faster-whisper:** установлен (отсутствовал)

## Core Pipeline — РАБОТАЕТ
```
POST /ingest/audio → файл + SQLite (status=pending)
POST /asr/transcribe → Whisper → SQLite (transcription + status=processed)
GET /digest/{date} → читает из SQLite → извлекает факты → markdown
LLM (Anthropic claude-3-haiku) → работает (860ms, 69 tokens)
```

## Следующие шаги
1. Тест с реальной речью (микрофон → listener → API)
2. Chain of Density summarization — разобраться почему саммари пустое
3. Structured Events (ADR-010) — обогащение транскрипций через LLM
4. Чистка 54 .md файлов в корне
5. Android app — оценить состояние

## Ключевые файлы
- API: `src/api/main.py`
- Edge: `src/edge/listener.py`
- ASR: `src/asr/transcribe.py`
- Digest: `src/digest/generator.py`
- Config: `src/utils/config.py`, `.env`
- Schema: `schema.sql`

## Для восстановления контекста
Reflexio 24/7: `D:/24 na 7/`. Цифровая память всей жизни. MVP не запускался. 104 .py, 16K строк, 15 модулей. Ядро: edge→asr→digest. Идея Centaur: structured events + паттерны. Phase: настройка окружения → первый запуск.
