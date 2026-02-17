# OSINT Knowledge Discovery System (KDS)

Автономная система добычи и проверки знаний для Reflexio 24/7.

## 🎯 Архитектура

KDS состоит из 4 основных компонентов:

1. **Collector** — сбор данных через Brave Search и Bright Data
2. **Contextor** — генерация R.C.T.F. промптов для LLM
3. **PEMM Agent** — стратегическое управление миссиями
4. **DeepConf** — Actor-Critic валидация с калибровкой доверия

## 🧩 Компоненты

### Collector (`collector.py`)

Собирает OSINT данные через два паттерна:

- **Паттерн A (Brave-first):** Поиск через Brave → извлечение через Bright Data
- **Паттерн B (BrightData-first):** Прямой скрапинг Goggle SERP → извлечение контента

```python
from src.osint.collector import gather_osint

sources = gather_osint("latest AI regulation news", limit=10)
```

### Contextor (`contextor.py`)

Генерирует структурированные R.C.T.F. промпты:

- **Role** — роль LLM (research analyst, fact checker и т.д.)
- **Context** — контекстные данные
- **Task** — конкретная задача
- **Format** — схема формата вывода

```python
from src.osint.contextor import build_rctf_prompt

prompt = build_rctf_prompt(
    role="research analyst",
    context_data={"query": "AI regulation"},
    task="Extract key claims",
    format_schema={"type": "object", ...},
    sources=sources,
)
```

### PEMM Agent (`pemm_agent.py`)

Координирует выполнение OSINT миссий:

1. Декомпозирует миссию на задачи
2. Собирает данные для каждой задачи
3. Генерирует утверждения через LLM
4. Валидирует через DeepConf
5. Сохраняет в Memory Bank

```python
from src.osint.pemm_agent import run_osint_mission, load_mission

mission = load_mission(Path("mission.json"))
result = run_osint_mission(mission)
```

### DeepConf (`deepconf.py`)

Валидирует утверждения используя Actor-Critic подход:

- **Actor (LLM)** — генерирует утверждения
- **Critic (LLM)** — проверяет утверждения на основе источников
- **Calibration** — калибрует уверенность используя Isotonic Regression

```python
from src.osint.deepconf import validate_claims

validated = validate_claims(claims, sources)
```

## 🚀 Использование

### Через Playbook

```bash
@playbook osint-mission --mission_file .cursor/osint/missions/example_mission.json
```

### CLI

```bash
# Запуск миссии
python -m src.osint.pemm_agent --mission mission.json --output result.json

# Валидация недавних утверждений
python -m src.osint.deepconf --validate recent
```

### Программно

```python
from src.osint.pemm_agent import run_osint_mission, load_mission
from pathlib import Path

mission = load_mission(Path("mission.json"))
result = run_osint_mission(mission)

print(f"Validated: {result.validated_claims}/{result.total_claims}")
print(f"Avg confidence: {result.avg_confidence:.2f}")
```

## 📋 Формат миссии

Миссия описывается в JSON:

```json
{
  "id": "mission_001",
  "name": "AI Regulation Research",
  "description": "Исследование последних новостей о регулировании AI",
  "tasks": [
    {
      "id": "task_1",
      "query": "latest AI regulation news",
      "role": "research analyst",
      "instruction": "Extract key claims...",
      "format_schema": {...},
      "max_results": 10
    }
  ],
  "target_confidence": 0.8
}
```

## 📊 Метрики

OSINT метрики автоматически добавляются в `cursor-metrics.json`:

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

## 🔗 Интеграция

KDS интегрируется с:

- **Memory Bank** — результаты сохраняются в `.cursor/memory/osint_research.md`
- **MCP Services** — использует Brave Search и Bright Data через MCP клиенты
- **Governance Loop** — метрики учитываются при вычислении reliability
- **Digest Generator** — может включать валидированные утверждения в дайджесты

## 🧠 PEMM Методология

**P**lanning → **E**xecution → **M**onitoring → **M**emory

1. **Planning** — декомпозиция миссии на задачи
2. **Execution** — сбор данных и генерация утверждений
3. **Monitoring** — валидация через DeepConf
4. **Memory** — сохранение в Memory Bank

---

**Reflexio 24/7 теперь может автономно добывать и проверять знания!** 🎯













