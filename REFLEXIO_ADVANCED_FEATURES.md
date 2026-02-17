# Reflexio 24/7 — Advanced Features

**Дополнительные возможности для полной автономности**

---

## 📡 Live Monitoring Agent

Автоматический запуск OSINT миссий по расписанию.

### Использование

```bash
# Регистрация миссии для мониторинга
python -m src.osint.monitoring_agent register \
  --mission .cursor/osint/missions/EnergyMarket_Updates_Nov2025.json \
  --interval 24

# Запуск всех миссий, которые должны быть выполнены
python -m src.osint.monitoring_agent run

# Список зарегистрированных миссий
python -m src.osint.monitoring_agent list
```

### Интеграция с cron

Добавьте в crontab для ежедневного запуска:

```bash
# Каждый день в 02:00
0 2 * * * cd /path/to/reflexio && python -m src.osint.monitoring_agent run
```

---

## 🔍 Knowledge Graph

Визуализация взаимосвязей утверждений из OSINT результатов.

### Построение графа

```bash
# Построить граф из всех результатов
python -m src.osint.knowledge_graph --build \
  --export .cursor/osint/knowledge_graph.json \
  --format json

# Экспорт в GraphML (для Gephi, yEd и т.д.)
python -m src.osint.knowledge_graph --build \
  --export .cursor/osint/knowledge_graph.graphml \
  --format graphml

# Экспорт в Cytoscape (для веб-визуализации)
python -m src.osint.knowledge_graph --build \
  --export .cursor/osint/knowledge_graph_cytoscape.json \
  --format cytoscape
```

### Формат данных

Граф содержит:
- **Nodes** — сущности (компании, суммы, даты)
- **Edges** — связи между сущностями
- **Weights** — количество упоминаний
- **Confidence** — средняя достоверность

---

## 🧩 Plugin Gateway

Система подключения внешних источников данных.

### Доступные плагины

- **Twitter** — поиск в Twitter
- **YouTube** — поиск в YouTube
- **Patents** — поиск патентов (USPTO/EPO)

### Использование

```bash
# Список доступных плагинов
python -m src.osint.plugin_gateway list

# Включить плагин
python -m src.osint.plugin_gateway enable --plugin twitter

# Поиск через плагины
python -m src.osint.plugin_gateway search --query "AI regulation"
```

### Создание собственного плагина

```python
from src.osint.plugin_gateway import Plugin, register_plugin

class MyPlugin(Plugin):
    def __init__(self):
        super().__init__("my_plugin", "My custom plugin")
    
    def search(self, query: str, **kwargs):
        # Ваша логика поиска
        return [{"title": "Result", "url": "https://..."}]

# Регистрация
register_plugin(MyPlugin())
```

---

## 🎯 Daily Energy Watch

Готовая миссия для ежедневного мониторинга энергетического рынка.

### Запуск

```bash
@playbook daily-energy-watch
```

### Что делает

1. Запускает миссию EnergyMarket_Updates_Nov2025
2. Обновляет Knowledge Graph
3. Анализирует здоровье знаний
4. Применяет DeepConf Feedback Loop

### Автоматизация

Добавьте в crontab:

```bash
# Каждый день в 03:00
0 3 * * * cd /path/to/reflexio && @playbook daily-energy-watch
```

---

## 🔄 Полный цикл автономности

### 1. Мониторинг
- Monitoring Agent запускает миссии по расписанию
- Результаты автоматически сохраняются

### 2. Обработка
- PEMM Agent декомпозирует миссии
- DeepConf валидирует утверждения
- Knowledge Graph строится автоматически

### 3. Адаптация
- Adaptive Scoring оценивает качество
- Feedback Loop реагирует на изменения
- Memory Curator обновляет знания

### 4. Расширение
- Plugin Gateway подключает новые источники
- Граф знаний растёт автоматически
- Система самообучается

---

## 📊 Интеграция всех компонентов

```
Monitoring Agent → OSINT Missions → PEMM Agent
                         ↓
                  Collector (Brave/Bright Data)
                         ↓
                  Contextor (R.C.T.F.)
                         ↓
                  Actor (LLM) → Claims
                         ↓
                  DeepConf (Critic)
                         ↓
                  Validated Claims
                         ↓
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
  Knowledge Graph   Memory Bank    Feedback Loop
        ↓                ↓                ↓
    Visualization   Curation      Adaptive Scoring
```

---

## ✅ Готовые компоненты

- ✅ Live Monitoring Agent
- ✅ Knowledge Graph
- ✅ Plugin Gateway (базовая структура)
- ✅ Daily Energy Watch playbook
- ✅ Пример миссии для энергетики

---

**Reflexio 24/7 теперь полностью автономен и расширяем!** 🚀✨













