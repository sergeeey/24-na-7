# Architectural Decisions — Reflexio 24/7

## Мигрировано из Cursor Memory + новые решения

### [legacy] ADR-001: Модульный монолит
- Решение: единое приложение, разбитое на изолированные модули
- Обоснование: баланс простоты и масштабируемости
- Переход к микросервисам возможен без переписывания

### [legacy] ADR-002: ASR — faster-whisper small int8
- Решение: локальная модель, не API
- Обоснование: офлайн-работа, нулевая стоимость, минимальная задержка
- Fallback: OpenAI Whisper API

### [legacy] ADR-003: VAD — webrtcvad
- Решение: webrtcvad (aggressiveness=2)
- Альтернатива: silero-vad (оставлен как опциональный)

### [legacy] ADR-004: Storage — SQLite → Supabase
- MVP: SQLite локально
- Прод: Supabase (PostgreSQL + Storage + pgvector для embeddings)

### [legacy] ADR-005: Zero-retention
- Аудио удаляется после успешной транскрипции
- PII маскируется на уровне текста перед LLM

### [2026-02-24] ADR-009: Видение — цифровая память, не диктофон
- Проблема: проект развивался как "умный диктофон + дайджест дня"
- Решение: переосмыслить как "цифровая память всей жизни"
- Что меняется:
  - Данные хранятся навсегда (не 24ч)
  - Semantic search по всей истории
  - Structured events вместо сырых транскриптов
  - Накопление → паттерны → предсказания
- Обоснование: это реальная ценность для пользователя

### [2026-02-24] ADR-010: Structured Events (из Centaur)
- Проблема: сырой транскрипт бесполезен для поиска и анализа
- Решение: каждый аудио-сегмент обогащается в structured event
  (timestamp, text, emotions, topics, decisions, tasks, speakers, confidence)
- Вдохновение: Centaur (Helmholtz AI) кодирует эксперименты как текст
- Реализация: LLM enrichment после транскрипции

### [2026-02-24] ADR-011: 80/20 — сначала core pipeline
- Проблема: 15 модулей, scope creep (OSINT, billing, monetization)
- Решение: фокус на ядре: Edge → ASR → Enrichment → Storage → Digest
- Всё остальное (OSINT, billing, analytics, voice_agent, MCP) — backlog
- Не удалять, но не развивать пока ядро не работает

### [2026-02-24] ADR-012: Предсказание через RAG, не fine-tuning
- Проблема: fine-tuning модели на личных данных — дорого, сложно, 70B не влезает
- Решение: RAG по накопленной базе structured events
- Инструменты: pgvector (Supabase) для embedding search
- Модели: Claude API / GPT-4o для обогащения, локальный Whisper для ASR
- RTX 5070 Ti (16GB) хватает на Whisper medium, не на LLM 70B
