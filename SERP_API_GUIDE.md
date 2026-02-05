# SERP API Integration Guide

**Интеграция SERP API для прямого доступа к Google, Bing и другим поисковым системам**

---

## 🎯 Возможности

### 1. Прямой доступ к поисковым системам
- **Google Search** — через Bright Data SERP API
- **Bing Search** — через Bright Data SERP API
- **Yahoo Search** — через Bright Data SERP API

### 2. Зональные прокси
- Разные зоны для разных типов миссий
- Автоматический выбор оптимальной зоны
- Отслеживание использования зон

### 3. Авто-ротация IP
- Ротация зон для распределения нагрузки
- Поддержка round-robin, least-used, random методов
- Автоматическая ротация после N запросов

---

## ⚙️ Конфигурация

### Zone Configuration

Файл `.cursor/config/brightdata_zones.json`:

```json
{
  "zones": {
    "serp_api1": {
      "name": "SERP API Zone 1",
      "type": "serp",
      "engines": ["google", "bing", "yahoo"],
      "priority": 1,
      "rotation_enabled": true
    },
    "news": {
      "name": "News Zone",
      "type": "content",
      "engines": [],
      "priority": 2,
      "rotation_enabled": true
    }
  },
  "rotation": {
    "enabled": true,
    "method": "round_robin"
  }
}
```

### Environment Variables

В `.env`:

```bash
# Bright Data API Key (обязательно для SERP API)
BRIGHTDATA_API_KEY=your_api_key_here

# Зона по умолчанию
BRIGHTDATA_ZONE=serp_api1
```

---

## 🚀 Использование

### Программно

```python
from src.osint.serp_collector import collect_serp_results

# Сбор результатов через Google SERP API
sources = collect_serp_results(
    query="latest AI news",
    search_engine="google",
    zone="serp_api1",
    limit=10,
    scrape_content=True,
)
```

### Через OSINT Collector

```python
from src.osint.collector import gather_osint

# Использование SERP API вместо Brave Search
sources = gather_osint(
    query="latest AI news",
    use_serp=True,
    search_engine="google",
    limit=10,
)
```

### Автоматический выбор зоны

```python
from src.osint.zone_manager import get_zone_for_mission

# Выбирает оптимальную зону для типа миссии
zone = get_zone_for_mission("serp")  # Для SERP миссий
zone = get_zone_for_mission("news")  # Для новостных миссий
```

---

## 📊 Типы зон

### SERP Zones
Для запросов к поисковым системам:
- `serp_api1` — основная зона для Google/Bing/Yahoo
- Поддерживает: `google`, `bing`, `yahoo`

### Content Zones
Для скрапинга контента:
- `news` — для новостных сайтов
- `academic` — для академических источников

---

## 🔄 Авто-ротация IP

### Методы ротации

1. **Round-Robin** — последовательная ротация зон
2. **Least-Used** — выбор наименее используемой зоны
3. **Random** — случайный выбор зоны

### Настройка

В `brightdata_zones.json`:

```json
{
  "rotation": {
    "enabled": true,
    "method": "round_robin"
  },
  "auto_rotation": {
    "enabled": true,
    "interval_requests": 10
  }
}
```

---

## 📈 Преимущества SERP API

### По сравнению с Brave Search:
- ✅ Прямой доступ к Google/Bing (оригинальные результаты)
- ✅ Больше результатов и вариантов
- ✅ Поддержка специфичных операторов поиска
- ✅ Актуальные данные в реальном времени

### По сравнению с обычным скрапингом:
- ✅ Обход блокировок и CAPTCHA
- ✅ Рендеринг JavaScript страниц
- ✅ Гео-ротация IP адресов
- ✅ Стабильность и надёжность

---

## 🧪 Тестирование

### Тест SERP API

```python
from src.mcp.clients import get_bright_client

bright = get_bright_client()

# Запрос через SERP API
serp_data = bright.scrape_serp(
    query="pizza",
    search_engine="google",
    zone="serp_api1",
)

print(serp_data)
```

### Тест Zone Manager

```python
from src.osint.zone_manager import get_zone_manager

manager = get_zone_manager()

# Выбор зоны для миссии
zone = manager.get_zone_for_mission("serp")
print(f"Selected zone: {zone}")

# Статистика использования
print(manager.zone_usage)
```

---

## 📊 Интеграция в миссии

### В JSON миссии

```json
{
  "id": "google_search_mission",
  "tasks": [
    {
      "query": "latest AI news",
      "use_serp": true,
      "search_engine": "google",
      "zone": "serp_api1"
    }
  ]
}
```

### Автоматический выбор

Если `zone` не указан, система автоматически выберет оптимальную зону на основе:
- Типа миссии
- Метода ротации
- Статистики использования

---

## 🔧 Решение проблем

### Ошибка: "API key required for SERP"

**Решение:** Убедитесь, что `BRIGHTDATA_API_KEY` установлен в `.env`

### Ошибка: "Zone not found"

**Решение:** Проверьте `.cursor/config/brightdata_zones.json` и убедитесь, что зона существует

### Медленные запросы

**Решение:**
1. Проверьте нагрузку в панели Bright Data
2. Попробуйте другую зону
3. Увеличьте timeout в настройках

---

**SERP API интегрирован в Reflexio OSINT KDS!** 🎯✨













