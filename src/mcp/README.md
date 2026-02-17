# MCP Intelligence Module

Интеллектуальный поиск и извлечение данных через Brave Search и Bright Data.

## 🎯 Возможности

- **Brave Search** — веб-поиск для разведки информации
- **Bright Data** — глубокое извлечение контента с веб-страниц
- **Автоматическая интеграция** — сохранение результатов в Memory Bank
- **Hook-based automation** — автоматический поиск при обнаружении новых тем

## 🚀 Использование

### CLI

```bash
# Простой поиск
python -m src.mcp.intelligence "latest AI regulation news"

# Поиск с сохранением в Memory Bank
python -m src.mcp.intelligence "quantum computing advances" --save

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

## ⚙️ Настройка

1. Получите API ключи:
   - Brave Search: https://brave.com/search/api/
   - Bright Data: https://brightdata.com/

2. Добавьте в `.env`:
   ```bash
   BRAVE_API_KEY=your_key_here
   BRIGHTDATA_API_KEY=your_key_here
   ```

3. Установите зависимости (опционально):
   ```bash
   pip install brave-search brightdata markdownify
   ```

   Примечание: Модуль работает и без официальных SDK, используя прямые HTTP запросы.

## 🔗 Интеграция с Hooks

Автоматический поиск при обнаружении новых тем:

```python
# В .cursor/hooks/on_event.py
on_new_topic_detected("AI regulation")
```

Результаты автоматически сохраняются в `.cursor/memory/external_research.md`.

## 📊 Метрики

MCP метрики автоматически добавляются в `cursor-metrics.json`:

```json
{
  "mcp": {
    "brave_latency_ms": 350,
    "brightdata_latency_ms": 1800,
    "brave_success_rate": 0.98,
    "brightdata_success_rate": 0.94
  }
}
```

## 🧠 Использование в Reflexio

Модуль автоматически интегрируется с:
- **Digest Generator** — добавляет внешние источники в дайджесты
- **Memory Bank** — сохраняет результаты исследований
- **Governance Loop** — учитывает метрики MCP при вычислении reliability













