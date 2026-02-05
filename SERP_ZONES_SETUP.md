# SERP API и Zone Management — Полная настройка

**Интеграция SERP API, зональных прокси и авто-ротации IP в Reflexio OSINT KDS**

---

## ✅ Что было добавлено

### 1. SERP API Integration
- ✅ Прямой доступ к Google, Bing, Yahoo через Bright Data SERP API
- ✅ Автоматический парсинг результатов поиска
- ✅ Извлечение полного контента страниц

### 2. Zone Management
- ✅ Управление зональными прокси
- ✅ Автоматический выбор зоны для типа миссии
- ✅ Отслеживание использования зон

### 3. Auto-Rotation
- ✅ Round-robin ротация
- ✅ Least-used ротация
- ✅ Random ротация
- ✅ Автоматическая ротация после N запросов

---

## 🔧 Настройка

### Шаг 1: Environment Variables

Добавьте в `.env`:

```bash
# Bright Data API Key (для SERP API)
BRIGHTDATA_API_KEY=your_api_key_here

# Зона по умолчанию
BRIGHTDATA_ZONE=serp_api1

# Proxy (опционально, если используете proxy вместо API)
BRIGHTDATA_PROXY_HTTP=https://brd-customer-USERNAME-zone-ZONE:PASSWORD@brd.superproxy.io:9515
BRIGHTDATA_PROXY_WS=wss://brd-customer-USERNAME-zone-ZONE:PASSWORD@brd.superproxy.io:9222
```

### Шаг 2: Zone Configuration

Файл `.cursor/config/brightdata_zones.json` уже создан с базовой конфигурацией:

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
    },
    "academic": {
      "name": "Academic Zone",
      "type": "content",
      "engines": [],
      "priority": 3,
      "rotation_enabled": false
    }
  },
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

### Шаг 3: Настройка зон в Bright Data

1. Войдите в панель Bright Data: https://brightdata.com/
2. Перейдите в раздел **Zones**
3. Создайте или выберите зоны:
   - `serp_api1` — для SERP запросов
   - `news` — для новостных сайтов
   - `academic` — для академических источников
4. Скопируйте **Zone ID** и обновите `.cursor/config/brightdata_zones.json`

### Шаг 4: Включение Auto-Rotation

В панели Bright Data для каждой зоны:
1. Откройте настройки зоны
2. Включите **IP Rotation**
3. Выберите метод ротации (если доступен)
4. Установите интервал ротации (если нужно)

---

## 🚀 Использование

### Использование SERP API в миссиях

```python
from src.osint.collector import gather_osint

# Сбор через Google SERP API
sources = gather_osint(
    query="latest AI news",
    use_serp=True,
    search_engine="google",
    zone="serp_api1",
    limit=10,
)
```

### Автоматический выбор зоны

```python
from src.osint.zone_manager import get_zone_for_mission

# Выбор зоны для типа миссии
zone = get_zone_for_mission("serp")      # Для SERP миссий
zone = get_zone_for_mission("news")      # Для новостных миссий
zone = get_zone_for_mission("academic")  # Для академических миссий
```

### В JSON миссиях

```json
{
  "id": "google_search_mission",
  "description": "Поиск через Google SERP API",
  "tasks": [
    {
      "query": "latest AI news",
      "use_serp": true,
      "search_engine": "google",
      "zone": "serp_api1",
      "max_results": 10
    }
  ]
}
```

---

## 📊 Методы ротации

### Round-Robin
Последовательная ротация зон:
```json
{
  "rotation": {
    "method": "round_robin"
  }
}
```

### Least-Used
Выбор наименее используемой зоны:
```json
{
  "rotation": {
    "method": "least_used"
  }
}
```

### Random
Случайный выбор зоны:
```json
{
  "rotation": {
    "method": "random"
  }
}
```

---

## 🔍 Мониторинг использования зон

Статистика сохраняется в `.cursor/metrics/zone_usage_stats.json`:

```json
{
  "last_updated": "2025-11-03T21:00:00Z",
  "usage": {
    "serp_api1": 45,
    "news": 12,
    "academic": 3
  },
  "total_requests": 60
}
```

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

# Выбор зоны
zone = manager.get_zone_for_mission("serp")
print(f"Selected zone: {zone}")

# Статистика
print(manager.zone_usage)
```

---

## 🎯 Преимущества

### SERP API vs Brave Search
- ✅ Прямой доступ к оригинальным результатам Google/Bing
- ✅ Больше результатов и вариантов
- ✅ Поддержка специфичных операторов поиска
- ✅ Актуальные данные в реальном времени

### Zone Management
- ✅ Распределение нагрузки между зонами
- ✅ Оптимизация для разных типов миссий
- ✅ Автоматический выбор оптимальной зоны
- ✅ Отслеживание использования

### Auto-Rotation
- ✅ Обход rate limits
- ✅ Повышение стабильности
- ✅ Распределение рисков
- ✅ Автоматическое управление

---

## 🔧 Решение проблем

### Ошибка: "API key required for SERP"

**Решение:** Убедитесь, что `BRIGHTDATA_API_KEY` установлен в `.env`

### Ошибка: "Zone not found"

**Решение:**
1. Проверьте `.cursor/config/brightdata_zones.json`
2. Убедитесь, что зона существует в панели Bright Data
3. Проверьте правильность Zone ID

### Медленные запросы

**Решение:**
1. Проверьте нагрузку в панели Bright Data
2. Попробуйте другую зону
3. Увеличьте timeout в настройках
4. Проверьте метод ротации

---

**SERP API и Zone Management готовы к использованию!** 🎯✨













