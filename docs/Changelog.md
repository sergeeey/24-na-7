# 📝 Changelog — Reflexio 24/7

Все значимые изменения в проекте документируются здесь.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).

---

## [2.1.0] - 2025-11-04

### Добавлено
- **Surpass Smart Noter Sprint — November 2025:**
  - **ASR Layer:**
    - Distil-Whisper для офлайн режима (≥ 30 мин без сети)
    - Улучшен whisper-large-v3-turbo (кластерный режим с retry)
    - WebRTC VAD v2 + adaptive gain control
    - Поддержка форматов Opus/AAC
    - Edge mode для офлайн транскрипции
  
  - **LLM & Reasoning:**
    - Эмоциональный анализ (EmoWhisper / pyAudioAnalysis)
    - Chain-of-Density с эмоциональным контекстом
    - Интеграция эмоций в Reflexio-loop
  
  - **UX Layer:**
    - Оптимизированный One-Tap Capture (< 300 мс)
    - PDF генерация для дайджестов
    - Вечерний cron (22:50) → Telegram дайджест
    - Кэширование embeddings в Smart Replay
  
  - **Memory & Context:**
    - Self-update памяти через Reflexio-loop
    - Синхронизация памяти с дайджестом
    - Оптимизация экономии токенов (≥ 30%) через кэширование
  
  - **Privacy & Governance:**
    - Активация Supabase RLS (tenant_id == auth.uid())
    - Локальное AES-256 шифрование аудио
    - Explainable AI (privacy.md)
    - Zero-retention для аудио > 24 ч
  
  - **Monetization & Growth:**
    - Freemium модель (30 мин/день бесплатно)
    - Stripe IAP интеграция
    - Referral система (invite 3 → +100 мин)
    - Метрики конверсии и аналитика

### Изменено
- Обновлён `src/asr/providers.py` — добавлен DistilWhisperProvider
- Обновлён `src/loop/reflexio_loop.py` — интеграция эмоций и self-update памяти
- Обновлён `src/digest/generator.py` — синхронизация с памятью
- Обновлён `src/storage/embeddings.py` — кэширование для экономии токенов

---

## [1.1.0] - 2025-11-04

### Добавлено
- **Integration Sprint — November 2025:**
  - **ASR Layer Upgrade:**
    - Поддержка whisper-large-v3-turbo (OpenAI API)
    - Интеграция WhisperX для word-level timestamps и диаризации
    - ParaKeet TDT v2 fallback для длинных аудио
    - Модульная архитектура провайдеров ASR
    - Тесты latency и accuracy (WER)
  
  - **LLM & Summarization Layer:**
    - Поддержка новых моделей: GPT-5-mini, Gemini-3-flash, Claude-4.5
    - Chain of Density (CoD) для уплотнения саммари
    - Few-Shot Actions с примерами JSON
    - DeepConf метрики (confidence score, token entropy)
    - Автоматическое улучшение через Refiner (Claude 4.5)
    - Интеграция в digest generator
  
  - **Voice & UX Layer:**
    - PWA структура (manifest.json, service-worker.js)
    - One-Tap Capture компонент (< 300 мс старт)
    - Smart Replay с embeddings и поиском по фразам
    - Voiceflow RAG интеграция для intent recognition
    - Fallback на GPT-mini при недоступности RAG
  
  - **Memory & Cognitive Layer:**
    - Letta SDK интеграция
    - Core Memory (предпочтения пользователя)
    - Session Memory (временные контексты)
    - Reflexio Loop с DeepConf-score
    - Pipeline: Summarizer → Critic → Refiner
  
  - **Infra / Governance:**
    - Миграция 0004_user_preferences.sql (opt_out_training флаг)
    - Тесты миграций Supabase + RLS
    - Security scans (Bandit, Ruff) в CI/CD
    - Обновлённый GitHub Actions pipeline

### Изменено
- Обновлён `src/asr/transcribe.py` — поддержка multiple providers
- Обновлён `src/llm/providers.py` — добавлен GoogleGeminiClient
- Обновлён `src/digest/generator.py` — интеграция улучшенного summarization
- Обновлён `src/api/main.py` — новые endpoints (/search/phrases, /voice/intent)

### Исправлено
- Улучшена обработка ошибок в WhisperX диаризации
- Исправлена интеграция embeddings для semantic search

---

## [1.0.0] - 2025-11-04

### Добавлено
- **Epic 1: Security Layer (SAFE + CoVe)**
  - SAFE валидаторы для PII detection, domain allowlist, file validation
  - CoVe (Consistency & Verification) для schema validation
  - Интеграция в API middleware
  - Playbook `security-validate`

- **Epic 2: LLM Integration**
  - Поддержка OpenAI и Anthropic провайдеров
  - Интеграция в `deepconf.py` для валидации утверждений
  - Fallback на эвристику при недоступности API
  - Smoke test `scripts/smoke_llm.py`

- **Epic 3: Data Layer**
  - Миграции SQLite → Supabase PostgreSQL
  - Миграции: `0001_init.sql`, `0002_indexes.sql`, `0003_rls_policies.sql`
  - CLI для миграций: `src/storage/migrate.py`
  - Единый DAL-слой: `src/storage/db.py`
  - Playbook `db-migrate`

- **Epic 4: Containerization + CI/CD**
  - `Dockerfile.api` — контейнер для FastAPI
  - `Dockerfile.worker` — контейнер для worker процессов
  - `docker-compose.yml` — оркестрация сервисов
  - `.github/workflows/ci.yml` — Continuous Integration
  - `.github/workflows/cd.yml` — Continuous Deployment

- **Epic 5: Observability**
  - `observability/prometheus.yml` — конфигурация Prometheus
  - `observability/alert_rules.yml` — правила алёртов
  - `observability/grafana_dashboards/reflexio.json` — Grafana dashboard
  - `/metrics/prometheus` endpoint в API
  - Playbook `observability-setup`

- **Epic 6: Hooks++ и Multi-Agent Isolation**
  - Расширение `.cursor/hooks/hooks.json` с дополнительными хуками
  - `scripts/agents/spawn_isolated.py` — изолированный запуск агентов через Git worktrees
  - Хуки: `on_agent_spawn`, `on_production_deploy`

- **Epic 7: Governance & Readiness Gates**
  - Production профиль в `.cursor/governance/profile.yaml`
  - Playbook `prod-readiness.yaml` — проверка готовности
  - Readiness gates: CEB-E Score ≥ 90, AI Reliability Index ≥ 0.95, Context Hit Rate ≥ 0.70
  - Автоматические политики: Auto Upgrade, Safety Mode, Self-Adaptive

- **Документация**
  - `docs/Project.md` — описание проекта и архитектуры
  - `docs/Changelog.md` — история изменений
  - `docs/STATUS_REPORT.md` — статус проекта
  - `docs/TASK_COMPLETION_PLAN.md` — план завершения задач

### Изменено
- Обновлён `src/storage/migrations/0002_indexes.sql` — исправлены ссылки на несуществующие таблицы
- Обновлён `.cursor/governance/profile.yaml` — установлен production профиль и Level 5
- Обновлён `.cursor/hooks/hooks.json` — добавлены новые хуки

### Исправлено
- Исправлены индексы в миграции 0002 (заменены `osint_claims` на `claims`)
- Исправлена структура миграций для корректной работы с Supabase

---

## [0.9.0] - 2025-11-03

### Добавлено
- OSINT KDS (Knowledge Discovery System)
- MCP интеграция (Brave Search, BrightData)
- DeepConf валидация утверждений
- Knowledge Graph построение

### Изменено
- Улучшена архитектура OSINT агентов
- Оптимизирована работа с MCP сервисами

---

## [0.8.0] - 2025-10-XX

### Добавлено
- Расширенные когнитивные метрики (семантика, лексика, динамика)
- Дневной дайджест с анализом информационной плотности
- Фильтрация речи (отличие речи от музыки/шума)

---

## [0.7.0] - 2025-10-XX

### Добавлено
- Базовая транскрипция через faster-whisper
- API для приёма аудио
- Хранение фактов в БД

---

## [0.6.0] - 2025-10-XX

### Добавлено
- Edge listener с VAD (Voice Activity Detection)
- Сегментация по тишине
- Автоматическая отправка на сервер

---

## [0.1.0] - 2025-09-XX

### Добавлено
- Начальная версия проекта
- Базовая структура
- MVP функциональность

---

## Типы изменений

- **Добавлено** — для новых функций
- **Изменено** — для изменений в существующей функциональности
- **Устарело** — для функций, которые скоро будут удалены
- **Удалено** — для удалённых функций
- **Исправлено** — для исправления ошибок
- **Безопасность** — для уязвимостей

---

**Последнее обновление:** 3 ноября 2025

