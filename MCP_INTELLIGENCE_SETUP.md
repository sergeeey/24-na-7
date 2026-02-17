# MCP Intelligence Pack — Установка и настройка

**Brave Search + Bright Data для Reflexio 24/7**

---

## 🎯 Что это даёт

- **Brave Search** → Веб-поиск для разведки информации
- **Bright Data** → Глубокое извлечение контента с веб-страниц
- **Автоматическая интеграция** → Сохранение в Memory Bank
- **Hook-based automation** → Автопоиск при обнаружении новых тем

---

## ⚙️ Быстрая настройка

### 1. Получите API ключи

- **Brave Search:** https://brave.com/search/api/
- **Bright Data:** https://brightdata.com/

### 2. Добавьте в `.env`

```bash
BRAVE_API_KEY=your_brave_api_key_here
BRIGHTDATA_API_KEY=your_brightdata_api_key_here
```

### 3. Опционально: установите SDK

```bash
pip install brave-search brightdata markdownify
```

**Примечание:** Модуль работает и без официальных SDK, используя прямые HTTP запросы.

---

## 🚀 Использование

### CLI

```bash
# Простой поиск
python -m src.mcp.intelligence "latest AI regulation news"

# С сохранением в Memory Bank
python -m src.mcp.intelligence "quantum computing" --save

# Только поиск без скрапинга
python -m src.mcp.intelligence "python best practices" --no-scrape
```

### Через Playbook

```bash
@playbook mcp-intelligence-probe --query "latest AI research"
```

### Программно

```python
from src.mcp.intelligence import combined_search_and_scrape

results = combined_search_and_scrape(
    query="latest AI regulation news",
    max_results=5,
    scrape_content=True,
)
```

---

## 🔗 Интеграция с Hooks

Автоматический поиск при обнаружении новых тем:

```bash
python .cursor/hooks/on_event.py new_topic_detected "AI regulation"
```

Результаты автоматически сохраняются в `.cursor/memory/external_research.md`.

---

## 📊 Метрики

MCP метрики автоматически собираются и добавляются в `cursor-metrics.json`:

```json
{
  "mcp": {
    "brave_latency_ms": 350,
    "brightdata_latency_ms": 1800,
    "last_check": "2025-11-03T20:30:00Z"
  }
}
```

Проверка здоровья:

```bash
python scripts/check_mcp_health.py --summary
@playbook validate-mcp
```

---

## ✅ Что создано

- ✅ `src/mcp/clients.py` — Клиенты для Brave Search и Bright Data
- ✅ `src/mcp/intelligence.py` — Интеллектуальный поиск и извлечение
- ✅ `.cursor/playbooks/mcp-intelligence.yaml` — Playbook для запуска
- ✅ Интеграция с hooks — Автопоиск при новых темах
- ✅ Валидация MCP — Проверка здоровья сервисов
- ✅ Конфигурация — Настройки в `config.py` и `.cursor/mcp.json`

---

## 🧠 Использование в Reflexio

Модуль автоматически интегрируется с:

- **Digest Generator** — Добавляет внешние источники в дайджесты
- **Memory Bank** — Сохраняет результаты исследований
- **Governance Loop** — Учитывает метрики MCP при вычислении reliability
- **Hooks System** — Автоматический поиск при обнаружении тем

---

**Reflexio 24/7 теперь имеет «когнитивное зрение» для поиска и извлечения внешних знаний!** 🎯













