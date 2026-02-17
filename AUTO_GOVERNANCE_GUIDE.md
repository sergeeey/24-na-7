# 🤖 Auto Governance Guide — Reflexio 24/7

**Руководство по автономному управлению и самоадаптации**

---

## 🎯 Обзор

**Reflexio 24/7** работает в режиме **Auto Governance** — система автоматически управляет собой через циклы аудита, метрик и обратной связи.

---

## 🔄 Цикл автоаудита

### Периодичность

| Задача | Частота | Скрипт/Playbook |
|--------|---------|-----------------|
| **Level 5 Validation** | Каждые 6 часов | `validate-level5` |
| **Proxy Diagnostics** | Раз в день | `proxy-diagnostics` |
| **Full Audit** | Раз в неделю | `audit-standard` |
| **Health Check** | Каждые 5 минут | `src/monitor/health.py` |
| **Observability Setup** | При старте | `observability-setup` |

### Автоматический Scheduler

**Сервис:** `scheduler` (в `docker-compose.yml`)  
**Файл:** `scripts/scheduler.py`  
**Логи:** `.cursor/logs/scheduler.log`

**Запуск:**
```bash
docker compose up -d scheduler
```

---

## 📊 Governance Telemetry

### Метрики в Supabase

Governance Loop автоматически отправляет метрики в таблицу `metrics`:

| Метрика | Описание | Обновление |
|---------|----------|------------|
| `ai_reliability` | AI Reliability Index | После каждого аудита |
| `context_hit_rate` | Context Hit Rate | После каждого аудита |
| `deepconf_avg` | Средняя DeepConf confidence | После OSINT миссий |
| `health_status` | Статус здоровья системы | Каждые 5 минут |

**Проверка:**
```python
from src.storage.db import get_db
db = get_db()
metrics = db.select("metrics", limit=10)
```

---

## 🎚️ Критерии перехода между уровнями

### Level 1 → Level 2 (Foundational)

**Условия:**
- Rules Engine настроен
- Memory Bank активен
- Базовые валидации проходят

**Действие:** `profile = "foundational"`

---

### Level 2 → Level 3 (Pro)

**Условии:**
- SAFE+CoVe валидация активна
- MCP Gateway настроен
- CEB-E Score ≥ 60

**Действие:** `profile = "pro"`

---

### Level 3 → Level 4 (Automated)

**Условия:**
- Governance Loop активен
- Автоматический аудит работает
- CEB-E Score ≥ 70
- AI Reliability ≥ 0.7

**Действие:** `profile = "automated"`

---

### Level 4 → Level 5 (Self-Adaptive)

**Условия:**
- CEB-E Score ≥ 90
- AI Reliability ≥ 0.95
- DeepConf avg ≥ 0.9
- Context Hit Rate ≥ 0.80

**Действие:** `profile = "production"`, `governance_mode = "self-adaptive"`

---

## 🔁 Автоматические Playbooks

### Запускаемые автоматически

| Playbook | Триггер | Частота |
|----------|---------|---------|
| `validate-level5` | Scheduler | Каждые 6 ч |
| `proxy-diagnostics` | Scheduler | Раз в день |
| `audit-standard` | Scheduler | Раз в неделю |
| `security-validate` | Hook: `on_config_change` | При изменении конфигурации |
| `db-migrate` | Hook: `on_env_change` | При изменении DB_BACKEND |
| `osint-mission` | Hook: `on_low_confidence` | При DeepConf < 0.8 |
| `level5-self-adaptive-upgrade` | Hook: `on_audit_success` | При Score ≥ 90 |

### Условия запуска

**Hooks настроены в:** `.cursor/hooks/hooks.json`

**Пример:**
```json
{
  "on_low_confidence": {
    "enabled": true,
    "trigger": "cursor-metrics.json",
    "condition": "avg_deepconf_confidence < 0.8",
    "action": "python src/osint/deepconf_feedback.py --trigger-auto-mission"
  }
}
```

---

## 📈 Мониторинг автономности

### Health Check Loop

**Компонент:** `src/monitor/health.py`  
**Запуск:** Автоматически при старте API (startup event)  
**Интервал:** 300 секунд (5 минут)

**Проверяет:**
- API доступность (`/health`)
- База данных подключение
- MCP сервисы (Brave, Bright Data)

**Результат:** Сохраняется в `metrics.health_status`

---

## 🎛️ Governance Profile

### Текущий профиль

**Файл:** `.cursor/governance/profile.yaml`

**Параметры:**
```yaml
active_profile: production
governance_mode: self-adaptive
auto_feedback: true
auto_audit_interval: 6h
auto_metrics_push: true
```

### Автоматическое обновление

**Триггер:** После каждого аудита  
**Скрипт:** `.cursor/metrics/governance_loop.py`

**Команда:**
```bash
python .cursor/metrics/governance_loop.py --apply results
```

---

## 🔍 Self-Adaptive Features

### 1. DeepConf Feedback Loop

**Компонент:** `src/osint/deepconf_feedback.py`

**Логика:**
- Если `avg_deepconf_confidence < 0.8` → запуск новой OSINT миссии
- Обновление `osint_governance.knowledge_health`
- Автоматическая регенерация устаревших утверждений

**Проверка:**
```bash
python src/osint/deepconf_feedback.py --apply
```

---

### 2. Adaptive Mission Scoring

**Компонент:** `src/osint/adaptive_scoring.py`

**Логика:**
- Приоритизация миссий по достоверности
- `mission_score = mean(confidence) * log(validated_claims + 1)`
- Автоматическая ротация зон для разных типов миссий

---

### 3. Memory Curation Agent

**Компонент:** `src/osint/memory_curator.py`

**Логика:**
- Удаление устаревших утверждений (> 90 дней)
- Пересчёт достоверности на новых данных
- Очистка опровергнутых утверждений

**Запуск:**
```bash
python src/osint/memory_curator.py --curate
```

---

## 📋 Проверка автономности

### Ежедневная проверка

```bash
# Проверка scheduler
docker logs reflexio-scheduler --tail 50

# Проверка метрик в Supabase
python - <<'PYCODE'
from src.storage.db import get_db
db = get_db()
health = db.select("metrics", filters={"metric_name": "health_status"}, limit=1)
print(f"Health status: {health[0]['metric_value'] if health else 'N/A'}")
PYCODE
```

### Еженедельная проверка

```bash
# Полный аудит
@playbook audit-standard

# Проверка governance
python .cursor/metrics/governance_loop.py --apply results

# Проверка готовности
@playbook prod-readiness
```

---

## 🚨 Алерты и уведомления

### Prometheus Alerts

**Файл:** `observability/alert_rules.yml`

**Настроенные алёрты:**
- `ReflexioAPIDown` — API недоступен > 2 мин
- `LLMErrorRateHigh` — ошибки LLM > 2%
- `DeepConfLowConfidence` — confidence < 0.8 > 10 мин
- `MCPServiceDown` — MCP сервис недоступен > 5 мин
- `HighLatency` — P95 latency > 5 сек

**Доступ:** Grafana Dashboard (`localhost:3000`)

---

## 🔧 Настройка автономности

### Включение/отключение компонентов

**В `.cursor/governance/profile.yaml`:**
```yaml
config:
  auto_audit: true              # Автоматический аудит
  auto_fix: true                # Автоматическое исправление
  adaptive_rules: true           # Адаптивные правила (Level 5)
  metrics_collection: true       # Сбор метрик
  strict_validation: true       # Строгая валидация
```

### Изменение интервалов

**В `scripts/scheduler.py`:**
```python
# Валидация Level 5 каждые 6 часов
if not self.should_run("validate-level5", 6.0):

# Health check каждые 5 минут
asyncio.create_task(periodic_check(interval=300))
```

---

## 📊 Метрики автономности

### KPI для Level 5

| Метрика | Целевое значение | Текущее |
|---------|------------------|---------|
| AI Reliability Index | ≥ 0.95 | ~0.79 |
| Context Hit Rate | ≥ 0.80 | ~0.69 |
| DeepConf Confidence | ≥ 0.80 | варьируется |
| CEB-E Score | ≥ 90 | 82 |
| Uptime | ≥ 99.9% | мониторинг |
| Auto-healing success | ≥ 95% | отслеживание |

---

## ✅ Чеклист автономности

- [x] Scheduler запущен и работает
- [x] Health check loop активен
- [x] Governance метрики пишутся в Supabase
- [x] Hooks настроены и активны
- [x] Автоматические playbooks запускаются
- [x] Prometheus алёрты настроены
- [x] Governance профиль = `production`
- [x] Auto-feedback включён

---

## 🎯 Следующие шаги

1. **Мониторинг метрик:** Отслеживание AI Reliability и Context Hit Rate
2. **Оптимизация thresholds:** Настройка порогов для автоматических действий
3. **Расширение алёртов:** Добавление новых правил в Prometheus
4. **Интеграция уведомлений:** Подключение Slack/Telegram для критических алёртов

---

**Последнее обновление:** 3 ноября 2025  
**Статус:** ✅ Auto Governance Active











