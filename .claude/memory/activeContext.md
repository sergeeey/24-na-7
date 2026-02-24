# Active Context — Reflexio 24/7

## Последнее обновление
2026-02-24 21:20

## Текущая фаза
**Core pipeline работает end-to-end → Улучшение качества (Chain of Density, Structured Events)**

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

### Что починено
- **Pipeline разрыв:** ingest и asr не писали в SQLite → добавлена запись в оба endpoint
- **policies.yaml:** битый YAML (экранирование `'` в regex) → починен
- **providers.py:** галлюцинированные модели (gpt-5-mini, claude-4-5) → исправлены на актуальные
- **providers.py:** баг в error handler Anthropic → починен (KeyError)
- **.env:** переключен на sqlite, LLM=anthropic (claude-3-haiku), SAFE=audit
- **metrics таблица:** создана в SQLite (health monitor больше не ругается)
- **faster-whisper:** установлен (отсутствовал)

### Android — СОБРАН И ПРОТЕСТИРОВАН
- **Build fix:** Upgrade Assistant сломал сборку (AGP 9.0.1, Kotlin 2.2.10, KSP 2.3.2)
  - Откатил на AGP 8.13.2, Kotlin 1.9.24, KSP 1.9.24-1.0.20
  - Room KSP: `C:\Windows\TEMP\` блокирует execution → добавлен `org.sqlite.tmpdir`
- **Device URL:** `ws://localhost:8000` + `adb reverse tcp:8000 tcp:8000`
- **Тест на Pixel 9 Pro:** полный pipeline работает!
  - Микрофон → VAD → WebSocket → Whisper → SQLite → Digest
  - Распознал русскую речь: "Как круто!", "Раз, два, три...", "вообще просто ништяк"
- **Эмулятор:** микрофон не пробрасывает реальный звук (известная проблема)

## Core Pipeline — РАБОТАЕТ END-TO-END
```
Android (Pixel 9 Pro) → VAD → WebSocket ws://localhost:8000/ws/ingest
  → файл + SQLite (status=pending)
  → Whisper ASR (faster-whisper, lang=ru detected)
  → SQLite (transcription + status=processed)
  → GET /digest/{date} → извлекает факты → markdown
  → LLM (Anthropic claude-3-haiku) → работает
```

## Дайджест за 2026-02-24
- 39 транскрипций, 9 фактов, 204 слова, 1.8 мин
- Информационная плотность: 88/100
- "Дневное саммари" пустое — Chain of Density не работает (backlog)

## Коммиты сессии
- `56159c5` — fix: connect core pipeline end-to-end, configure LLM and SQLite
- `1a7124c` — feat: add audio spectrum visualizer to Android app
- `f5efc62` — fix: revert Upgrade Assistant breakage, fix Room KSP build on Windows

## Следующие шаги
1. **Chain of Density summarization** — разобраться почему "Дневное саммари" пустое
2. **Structured Events (ADR-010)** — обогащение транскрипций через LLM
3. **Whisper галлюцинации** — фильтр "Thank you" / "You" на тихих сегментах
4. Чистка 54 .md файлов в корне
5. Android: offline queue, retry logic

## Ключевые файлы
- API: `src/api/main.py`
- WebSocket: `src/api/routers/websocket.py`
- Edge: `src/edge/listener.py`
- ASR: `src/asr/transcribe.py`
- Digest: `src/digest/generator.py`
- Config: `src/utils/config.py`, `.env`
- Android: `android/app/build.gradle.kts`

## Для восстановления контекста
Reflexio 24/7: `D:/24 na 7/`. Цифровая память всей жизни. Pipeline работает end-to-end: Android Pixel 9 Pro → VAD → WebSocket → Whisper → SQLite → Digest. 3 коммита запушены (f5efc62). Следующее: Chain of Density (пустое саммари), Structured Events, фильтр Whisper-галлюцинаций. Устройство подключается через `adb reverse tcp:8000 tcp:8000`.
