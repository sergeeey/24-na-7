# Первая OSINT Миссия — Руководство по запуску

**Быстрый старт Reflexio OSINT KDS**

---

## ✅ Шаг 1: Проверка готовности

Перед запуском проверьте, что система готова:

```bash
python scripts/check_osint_readiness.py
```

Скрипт проверит:
- ✅ Наличие API ключей в `.env`
- ✅ Наличие миссий в `.cursor/osint/missions/`
- ✅ Доступность всех модулей OSINT
- ✅ Наличие необходимых директорий

---

## 🔑 Шаг 2: Настройка API ключей и Proxy

Создайте файл `.env` в корне проекта (если его нет):

```bash
# .env
BRAVE_API_KEY=BSAUyRp7HWX4-kGYYO6rnukUrNyLojU

# Bright Data Proxy (рекомендуется)
BRIGHTDATA_PROXY_HTTP=https://brd-customer-hl_16abad82-zone-tttt:46ju8s7m4bcz@brd.superproxy.io:9515
BRIGHTDATA_PROXY_WS=wss://brd-customer-hl_16abad82-zone-tttt:46ju8s7m4bcz@brd.superproxy.io:9222

# Альтернатива: Bright Data API Key
# BRIGHTDATA_API_KEY=your_brightdata_api_key_here
```

**Где получить ключи:**

- **Brave Search**: https://brave.com/search/api/
- **Bright Data Proxy**: Панель управления Bright Data → Zones → Endpoints

---

## 🚀 Шаг 3: Запуск первой миссии

### Вариант 1: Через Playbook (рекомендуется)

```bash
@playbook osint-mission --mission_file .cursor/osint/missions/first_mission.json
```

### Вариант 2: Напрямую через Python

```bash
python -m src.osint.pemm_agent \
  --mission .cursor/osint/missions/first_mission.json \
  --output .cursor/osint/results/first_mission_result.json
```

---

## 📊 Что происходит во время миссии

1. **Collector** собирает данные:
   - Поиск через Brave Search по запросу
   - Извлечение контента через Bright Data
   - Структурирование источников

2. **Contextor** создаёт R.C.T.F. промпт:
   - Role: research analyst
   - Context: собранные источники
   - Task: извлечение ключевых новостей
   - Format: структурированный JSON

3. **Actor (LLM)** генерирует утверждения:
   - Извлечение фактов из источников
   - Структурирование по заданному формату

4. **DeepConf** валидирует утверждения:
   - Actor-Critic проверка
   - Калибровка confidence
   - Определение статуса (supported/refuted/uncertain)

5. **Memory Curation** сохраняет результаты:
   - Валидированные утверждения в Memory Bank
   - Обновление метрик в cursor-metrics.json

---

## 📄 Шаг 4: Проверка результатов

### JSON результат миссии

```bash
cat .cursor/osint/results/first_mission_result_*.json
```

Содержит:
- `mission_id` — ID миссии
- `tasks_completed` — количество выполненных задач
- `total_claims` — общее количество утверждений
- `validated_claims` — количество валидированных
- `avg_confidence` — средняя уверенность
- `claims` — список валидированных утверждений

### Memory Bank

```bash
cat .cursor/memory/osint_research.md
```

Содержит:
- Валидированные утверждения с метками ✅/❌/⚠️
- Confidence scores
- Источники (source_urls)
- Evidence для каждого утверждения

### Метрики

```bash
cat cursor-metrics.json
```

Обновлённые метрики:
```json
{
  "metrics": {
    "osint": {
      "avg_deepconf_confidence": 0.85,
      "missions_completed": 1,
      "total_claims": 10,
      "validated_claims": 8
    }
  }
}
```

---

## 🔍 Шаг 5: Проверка системы

После первой миссии проверьте статус системы:

```bash
@playbook validate-level5
```

или

```bash
python .cursor/validation/level5_validation.py
```

---

## 🔄 Шаг 6: Автоматический режим (опционально)

Для включения автономной работы:

```bash
@playbook level5-self-adaptive-upgrade
```

Это активирует:
- DeepConf Feedback Loop
- Adaptive Mission Scoring
- Memory Curation Agent
- Автоматическую адаптацию

---

## 🎯 Создание собственной миссии

### Простой пример

Создайте файл `.cursor/osint/missions/my_mission.json`:

```json
{
  "id": "my_mission",
  "name": "My Custom Mission",
  "description": "Описание миссии",
  "tasks": [
    {
      "id": "task_1",
      "query": "ваш поисковый запрос",
      "role": "research analyst",
      "instruction": "Инструкция для извлечения данных",
      "format_schema": {
        "type": "object",
        "properties": {
          "claims": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "text": {"type": "string"},
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

Запуск:
```bash
@playbook osint-mission --mission_file .cursor/osint/missions/my_mission.json
```

---

## ⚠️ Решение проблем

### Ошибка: "API key not found"

**Решение:** Проверьте `.env` файл и убедитесь, что ключи установлены:
```bash
cat .env | grep API_KEY
```

### Ошибка: "No sources collected"

**Решение:** 
1. Проверьте доступность API (Brave/Bright Data)
2. Убедитесь, что ключи валидны
3. Попробуйте другой поисковый запрос

### Ошибка: "Module not found"

**Решение:** Убедитесь, что все зависимости установлены:
```bash
pip install -r requirements.txt
```

---

## 📈 Следующие шаги

После успешного запуска первой миссии:

1. **Проверьте метрики:**
   ```bash
   python -m src.osint.adaptive_scoring --analyze
   ```

2. **Запустите курацию памяти:**
   ```bash
   python -m src.osint.memory_curator --max-age 30 --threshold 0.8
   ```

3. **Примените Feedback Loop:**
   ```bash
   python -m src.osint.deepconf_feedback --apply
   ```

4. **Зарегистрируйте миссию для мониторинга:**
   ```bash
   python -m src.osint.monitoring_agent register \
     --mission .cursor/osint/missions/first_mission.json \
     --interval 24
   ```

---

**Готово! Reflexio 24/7 теперь собирает и проверяет знания!** 🎯✨

