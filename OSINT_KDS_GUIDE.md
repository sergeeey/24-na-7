# OSINT Knowledge Discovery System (KDS) — Полное руководство

**Автономная система добычи и проверки знаний для Reflexio 24/7**

---

## 🎯 Что это такое

KDS — это интегрированный конвейер для автономной добычи и проверки знаний, который превращает Reflexio 24/7 из "системы записи речи" в **автономную исследовательскую платформу**.

Система использует:
- **Brave Search** — независимый поисковый индекс
- **Bright Data** — гарантированный доступ к реальному вебу
- **PEMM методология** — структурированное управление миссиями
- **DeepConf** — Actor-Critic валидация с калибровкой доверия

---

## 🧩 Архитектура KDS

```
Mission → PEMM Agent → Collector → Contextor → Actor (LLM) → DeepConf → Memory Bank
           ↓              ↓           ↓           ↓              ↓
        Planning      Brave+      R.C.T.F.    Claims        Validated
                     BrightData    Prompts   Generation     Claims
```

### Компоненты

1. **Collector** (`src/osint/collector.py`)
   - Паттерн A: Brave-first (поиск → извлечение)
   - Паттерн B: BrightData-first (Goggle SERP → извлечение)

2. **Contextor** (`src/osint/contextor.py`)
   - Генерация R.C.T.F. промптов (Role-Context-Task-Format)
   - Извлечение утверждений из LLM ответов

3. **PEMM Agent** (`src/osint/pemm_agent.py`)
   - Декомпозиция миссий на задачи
   - Координация всех компонентов
   - Сохранение в Memory Bank

4. **DeepConf** (`src/osint/deepconf.py`)
   - Actor-Critic валидация
   - Калибровка уверенности (Isotonic Regression)
   - Три статуса: supported / refuted / uncertain

---

## 🚀 Быстрый старт

### 1. Создайте миссию

Создайте JSON файл с описанием миссии:

```json
{
  "id": "ai_regulation_research",
  "name": "AI Regulation Research",
  "description": "Исследование последних новостей о регулировании AI",
  "tasks": [
    {
      "id": "task_1",
      "query": "latest AI regulation news 2025",
      "role": "research analyst",
      "instruction": "Extract key claims about AI regulation. Focus on dates, regulations, and stakeholders.",
      "format_schema": {
        "type": "object",
        "properties": {
          "claims": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "text": {"type": "string"},
                "category": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
              }
            }
          }
        }
      },
      "max_results": 10
    }
  ],
  "target_confidence": 0.8
}
```

### 2. Запустите миссию

```bash
@playbook osint-mission --mission_file .cursor/osint/missions/your_mission.json
```

### 3. Проверьте результаты

```bash
# Результаты миссии
cat .cursor/osint/results/your_mission_result.json

# Сохранено в Memory Bank
cat .cursor/memory/osint_research.md
```

---

## 📋 Формат миссии

### Обязательные поля

- `id` — уникальный идентификатор миссии
- `name` — название миссии
- `description` — описание
- `tasks` — массив задач

### Поля задачи (Task)

- `id` — идентификатор задачи
- `query` — поисковый запрос
- `role` — роль для LLM (например, "research analyst", "fact checker")
- `instruction` — инструкция для извлечения утверждений
- `format_schema` — JSON schema для формата вывода
- `max_results` — максимальное количество результатов
- `goggle_url` (опционально) — URL Goggle для паттерна B

---

## 🧠 PEMM Методология

**P**lanning → **E**xecution → **M**onitoring → **M**emory

1. **Planning** — декомпозиция миссии на задачи
2. **Execution** — сбор данных (Collector) → генерация утверждений (Actor)
3. **Monitoring** — валидация через DeepConf (Critic)
4. **Memory** — сохранение валидированных утверждений

---

## 🔬 DeepConf Валидация

Actor-Critic подход:

1. **Actor (LLM)** генерирует утверждения из источников
2. **Critic (LLM)** проверяет каждое утверждение на основе источников
3. **Calibration** калибрует уверенность используя Isotonic Regression

### Статусы валидации

- `supported` — утверждение поддерживается источниками
- `refuted` — утверждение опровергается источниками
- `uncertain` — недостаточно данных для валидации

---

## 📊 Метрики

OSINT метрики автоматически собираются:

```json
{
  "osint": {
    "missions_completed": 3,
    "total_claims": 124,
    "validated_claims": 98,
    "avg_deepconf_confidence": 0.93,
    "last_mission": "2025-11-03T20:30:00Z"
  }
}
```

Метрики учитываются в:
- `cursor-metrics.json`
- Governance Loop (влияют на AI Reliability Index)
- Аудит отчётах

---

## 🔗 Интеграция с Reflexio

### Memory Bank

Результаты автоматически сохраняются в:
- `.cursor/memory/osint_research.md` — markdown отчёт
- Структурированный формат для интеграции с дайджестами

### Digest Generator

Валидированные утверждения могут включаться в ежедневные дайджесты.

### Governance Loop

Метрики OSINT учитываются при вычислении AI Reliability Index.

---

## 🛠️ Использование программно

```python
from src.osint.pemm_agent import run_osint_mission, load_mission
from pathlib import Path

# Загрузить миссию
mission = load_mission(Path("mission.json"))

# Выполнить миссию
result = run_osint_mission(mission)

# Результаты
print(f"Validated: {result.validated_claims}/{result.total_claims}")
print(f"Avg confidence: {result.avg_confidence:.2f}")

# Валидированные утверждения
for vclaim in result.claims:
    if vclaim.validation_status == "supported":
        print(f"✅ {vclaim.claim.text}")
        print(f"   Confidence: {vclaim.calibrated_confidence:.2f}")
```

---

## 📁 Структура файлов

```
src/osint/
├── collector.py       # Сбор данных (Brave + Bright Data)
├── contextor.py       # R.C.T.F. промпты
├── pemm_agent.py      # PEMM агент (координатор)
├── deepconf.py        # Actor-Critic валидация
└── schemas.py         # Pydantic схемы

.cursor/osint/
└── missions/          # JSON файлы миссий

.cursor/osint/results/ # Результаты выполнения миссий
```

---

## ⚙️ Конфигурация

### API ключи

Добавьте в `.env`:

```bash
BRAVE_API_KEY=your_key
BRIGHTDATA_API_KEY=your_key
```

### Зависимости (опционально)

```bash
pip install brave-search brightdata markdownify scikit-learn
```

Модуль работает и без официальных SDK.

---

## 🎯 Примеры миссий

### Исследование темы

```json
{
  "id": "topic_research",
  "name": "Topic Research",
  "tasks": [{
    "query": "quantum computing breakthroughs 2025",
    "role": "research analyst",
    "instruction": "Extract key scientific breakthroughs",
    "max_results": 10
  }]
}
```

### Мониторинг новостей

```json
{
  "id": "news_monitor",
  "name": "News Monitor",
  "tasks": [{
    "query": "latest AI regulation news",
    "role": "news analyst",
    "instruction": "Extract news items with dates and sources",
    "max_results": 15
  }]
}
```

---

## ✅ Критерии успеха миссии

- `tasks_completed` == `total_tasks`
- `avg_confidence` >= `target_confidence`
- `validated_claims` / `total_claims` >= 0.7 (70% валидированы)
- Нет критических ошибок

---

**Reflexio 24/7 теперь может автономно добывать и проверять знания из внешних источников!** 🎯













