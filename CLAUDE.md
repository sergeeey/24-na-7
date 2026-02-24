# CLAUDE.md — Reflexio 24/7
# Цифровая память всей жизни
# Версия: 2.0 | Обновлено: 2026-02-24

---

## ВИДЕНИЕ

Reflexio — не "умный диктофон", а **цифровая память всей жизни**.
Система непрерывно захватывает речь, обогащает контекстом (кто, где, когда, эмоции),
накапливает в постоянном хранилище и позволяет искать, анализировать, предсказывать.

**Ключевой вопрос пользователя:** "О чём я говорил с Маратом в январе?"
**Ответ системы:** находит, суммирует, показывает паттерны.

Вдохновение: модель Centaur (Helmholtz AI + DeepMind, Nature 2025) —
каждое событие жизни кодируется как structured text с контекстом,
накопление данных даёт паттерны поведения и предсказания.

---

## АРХИТЕКТУРА

```
Edge (телефон/ПК)          Backend (FastAPI)           Intelligence
─────────────────          ─────────────────           ─────────────
Микрофон                   POST /ingest/audio          Semantic search
  → VAD (webrtcvad)          → Сохранение WAV          Паттерны поведения
  → Фильтр музыки/шума      → ASR (faster-whisper)     Предсказания
  → Авто-отправка            → Enrichment (LLM)         Дайджест дня
                             → Structured Event          Cognitive metrics
                             → Storage (SQLite→Supabase)
```

### Ключевая модель данных: Structured Event

Не сырой транскрипт, а размеченное событие:
```json
{
  "timestamp": "2026-02-24T09:15:00",
  "text": "Обсуждали бюджет Q2 с Маратом",
  "emotions": ["уверенность"],
  "topics": ["бюджет", "Q2"],
  "decisions": ["сократить на 15%"],
  "tasks": ["подготовить таблицу к пятнице"],
  "speakers": ["я", "Марат"],
  "location": null,
  "confidence": 0.87
}
```

---

## СТЕК

- **Python 3.11+**, FastAPI, uvicorn
- **ASR:** faster-whisper (small int8, локально)
- **VAD:** webrtcvad (aggressiveness=2)
- **LLM:** OpenAI / Anthropic API (enrichment, summarization)
- **Storage:** SQLite (MVP) → Supabase (PostgreSQL + pgvector)
- **Summarization:** Chain of Density → Critic → Refiner (ReflexioLoop)
- **Memory:** CoreMemory (предпочтения) + SessionMemory (контексты)
- **Logging:** structlog (JSON)
- **Android:** Kotlin app (Gradle) — будущее
- **PWA:** webapp/pwa — будущее

---

## КОМАНДЫ

```bash
# Установка
cd "D:/24 na 7"
pip install -e ".[dev]"

# API сервер
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Edge listener (запись с микрофона)
python src/edge/listener.py

# Тесты
pytest tests/
pytest tests/ --cov=src --cov-report=html

# Линтинг
ruff check src tests
black src tests
mypy src
```

---

## КЛЮЧЕВЫЕ ПУТИ

```
D:/24 na 7/
├── src/
│   ├── api/main.py              # FastAPI app, 8 роутеров
│   ├── api/routers/             # ingest, asr, digest, metrics, search, voice, ws, analyze
│   ├── edge/listener.py         # VAD + запись + авто-отправка
│   ├── edge/filters.py          # Фильтр музыки/шума
│   ├── asr/transcribe.py        # faster-whisper wrapper
│   ├── digest/generator.py      # Дайджест (markdown/json/pdf)
│   ├── digest/analyzer.py       # Анализ плотности
│   ├── summarizer/              # Chain of Density, Critic, Refiner, Emotions
│   ├── loop/reflexio_loop.py    # Summarizer → Critic → Refiner pipeline
│   ├── memory/core_memory.py    # Долгосрочная память (предпочтения, паттерны)
│   ├── memory/session_memory.py # Сессионная память
│   ├── llm/providers.py         # OpenAI/Anthropic клиенты
│   ├── storage/                 # SQLite persist, миграции
│   └── utils/config.py          # Pydantic Settings из .env
├── tests/                       # 25+ тест-файлов
├── schema.sql                   # SQLite schema (ingest_queue, transcriptions, facts, digests)
├── android/                     # Kotlin app (будущее)
├── webapp/pwa/                  # PWA (будущее)
└── .env                         # Конфигурация (из .env.example)
```

---

## ПРАВИЛА

### Privacy & Security
- **Zero-retention:** аудио удаляется после успешной транскрипции
- **PII:** маскировать ИИН, телефоны, счета в транскриптах перед LLM
- **Secrets:** только через .env, никогда в коде
- **Запись звонков:** НЕТ (юридические ограничения КЗ)

### Код
- Python 3.11+, type hints
- structlog вместо print()
- Pydantic для валидации входов/выходов
- Комментарии `# ПОЧЕМУ:` перед нетривиальными решениями
- Conventional commits: feat/fix/docs/refactor/test

### При работе с проектом
- НЕ менять .env.example без явной необходимости
- НЕ добавлять новые зависимости без обоснования
- НЕ создавать новые .md файлы (их уже 54 — это проблема, не фича)
- Предпочитать починку существующего кода созданию нового

---

## ТЕКУЩИЙ СТАТУС

**Phase:** MVP не запускался end-to-end
**Код:** 104 .py файла, ~16K строк
**Тесты:** 25+ файлов, target coverage 80%
**Проблемы:**
- 54 .md файла в корне (AI-generated bloat)
- 15 модулей в src/ (scope creep: OSINT, billing, monetization — преждевременно)
- Никогда не тестировался end-to-end
- Зависимость от LLM API и Letta SDK (может не быть настроено)

**Приоритет:** запустить core pipeline (Edge → ASR → Digest)

---

## CENTAUR-ИНСАЙТЫ (для будущего)

Из модели Centaur (Helmholtz AI, Nature 2025):
1. **Событие = structured text** — каждый момент жизни кодируется с контекстом
2. **Накопление → паттерны** — не дайджест и забыл, а растущая база знаний
3. **Предсказание поведения** — через RAG по истории (не fine-tuning)
4. **Когнитивное профилирование** — как человек принимает решения, его паттерны
5. **Fraud scoring для себя** — профиль нормы → отклонения → инсайты
