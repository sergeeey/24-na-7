# 🚀 Production Launch Checklist — Reflexio 24/7

**Дата:** 3 ноября 2025  
**Версия:** 1.0  
**Цель:** Пошаговая инструкция для запуска в продакшене

---

## ✅ Pre-Launch Checklist

### 1. Переменные окружения

**⚠️ ВАЖНО: Два "мира" ключей!**

#### A. Python-приложение (`.env` файл)

- [ ] Файл `.env` создан **в корне проекта** (не `.env.example`!)
- [ ] `DB_BACKEND=supabase`
- [ ] `SUPABASE_URL=https://your-project.supabase.co`
- [ ] `SUPABASE_ANON_KEY=your_anon_key`
- [ ] `SUPABASE_SERVICE_ROLE=your_service_key` (опционально, для RLS обхода)
- [ ] `LLM_PROVIDER=openai` (или `anthropic`)
- [ ] `OPENAI_API_KEY=sk-...` (или `ANTHROPIC_API_KEY=...`)
- [ ] `BRAVE_API_KEY=...` (для OSINT HTTP-клиента)
- [ ] `BRIGHTDATA_API_KEY=...` (для OSINT HTTP-клиента)
- [ ] `SAFE_MODE=strict`
- [ ] `SAFE_PII_MASK=1`
- [ ] Все ключи проверены и валидны
- [ ] **Нет кавычек** вокруг значений
- [ ] **Нет пробелов** вокруг `=`

**Проверка:**
```bash
python scripts/check_api_keys.py
python scripts/prod_verification.py
```

#### B. MCP-серверы Cursor (отдельно!)

**MCP серверы Cursor НЕ читают `.env` проекта!**

- [ ] Открыть Cursor Settings → Features → MCP → Configure
- [ ] Включить серверы `brave` и `brightdata`
- [ ] Добавить переменные:
  - `BRAVE_API_KEY` (в настройках MCP или системных переменных)
  - `BRIGHTDATA_API_KEY` или `BRIGHTDATA_PROXY_HTTP` (в настройках MCP или системных переменных)
- [ ] Сохранить и выполнить **Reload Window** (`Cmd/Ctrl + Shift + P`)
- [ ] Проверить, что серверы **зелёные** в списке MCP

**Проверка:**
```bash
@playbook validate-mcp-config
```

**Подробнее:** `API_KEYS_SETUP.md`

---

### 2. FFmpeg установлен

- [ ] FFmpeg установлен в системе

**Установка:**

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Linux (Fedora/RHEL):**
```bash
sudo dnf install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
- Скачать с [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
- Добавить в PATH

**Проверка:**
```bash
ffmpeg -version
```

**Для Docker:**
FFmpeg должен быть включён в `Dockerfile.api` (проверьте наличие установки)

---

### 3. Миграции Supabase

- [ ] Миграции применены в Supabase Dashboard

**Шаги:**

1. Открыть Supabase Dashboard → **SQL Editor**

2. Выполнить `src/storage/migrations/0001_init.sql`:
   ```sql
   -- Скопировать содержимое файла и выполнить
   ```

3. Выполнить `src/storage/migrations/0003_rls_policies.sql`:
   ```sql
   -- Скопировать содержимое файла и выполнить
   ```

4. Проверить создание таблиц:
   - `audio_meta`
   - `text_entries`
   - `insights`
   - `claims`
   - `missions`
   - `metrics`

**Или через playbook:**
```bash
@playbook db-migrate --target supabase --apply-schema
```

**Проверка подключения:**
```bash
python scripts/test_supabase.py
```

---

### 4. Docker контейнеры

- [ ] Docker и Docker Compose установлены
- [ ] `docker-compose.yml` настроен

**Установка Docker:**
- Linux: [docs.docker.com/get-docker](https://docs.docker.com/get-docker/)
- macOS: [docs.docker.com/desktop/mac/install](https://docs.docker.com/desktop/mac/install/)
- Windows: [docs.docker.com/desktop/windows/install](https://docs.docker.com/desktop/windows/install/)

**Проверка:**
```bash
docker --version
docker compose version
```

**Сборка и запуск:**
```bash
# Сборка образов
docker compose build

# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps
```

**Ожидаемые сервисы:**
- `reflexio-api` — основной API
- `reflexio-worker` — worker процессы
- `reflexio-scheduler` — планировщик задач
- `reflexio-prometheus` — метрики (если включён profile `observability`)
- `reflexio-grafana` — дашборды (если включён profile `observability`)

---

### 5. Проверка работоспособности

- [ ] Все контейнеры запущены
- [ ] Health endpoint отвечает
- [ ] Метрики доступны
- [ ] Логи без критических ошибок

**Проверки:**

**1. Статус контейнеров:**
```bash
docker compose ps
```

**2. Health check:**
```bash
curl http://localhost:8000/health
```

**Ожидаемый ответ:**
```json
{
  "status": "ok",
  "service": "reflexio",
  "version": "0.1.0"
}
```

**3. Метрики:**
```bash
curl http://localhost:8000/metrics/prometheus
```

**4. Логи:**
```bash
# API
docker compose logs api --tail 50

# Scheduler
docker compose logs scheduler --tail 50

# Worker
docker compose logs worker --tail 50
```

**5. Scheduler logs:**
```bash
cat .cursor/logs/scheduler.log | tail -20
```

---

### 6. Observability (опционально)

- [ ] Prometheus доступен (`localhost:9090`)
- [ ] Grafana доступна (`localhost:3000`)
- [ ] Dashboard импортирован
- [ ] Алёрты настроены

**Запуск observability stack:**
```bash
docker compose --profile observability up -d prometheus grafana
```

**Доступ:**
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin / admin)

**Импорт dashboard:**
1. Grafana → Dashboards → Import
2. Загрузить `observability/grafana_dashboards/reflexio.json`

---

### 7. Автономный цикл

- [ ] Scheduler запущен
- [ ] Health monitor активен
- [ ] Governance loop работает
- [ ] Hooks настроены

**Проверка:**

**1. Верификация автономного цикла:**
```bash
python scripts/verify_autonomous_cycle.py
```

**2. Отправка метрик:**
```bash
python .cursor/metrics/governance_loop.py --push-metrics
```

**3. Проверка хуков:**
```bash
python .cursor/hooks/on_event.py low_confidence_detected "Test"
```

**4. Проверка метрик в Supabase:**
```bash
python - <<'PYCODE'
from src.storage.db import get_db_backend
db = get_db_backend()
metrics = db.select("metrics", limit=10)
for m in metrics:
    print(f"{m['metric_name']}: {m['metric_value']}")
PYCODE
```

---

## 🚨 Troubleshooting

### Проблема: Контейнер не запускается

**Решение:**
```bash
# Проверить логи
docker compose logs <service_name>

# Пересобрать
docker compose build --no-cache <service_name>
docker compose up -d <service_name>
```

### Проблема: FFmpeg не найден

**Решение:**
```bash
# Проверить в контейнере
docker compose exec api ffmpeg -version

# Если отсутствует, добавить в Dockerfile.api:
# RUN apt-get update && apt-get install -y ffmpeg
```

### Проблема: Supabase недоступен

**Решение:**
1. Проверить `SUPABASE_URL` и `SUPABASE_ANON_KEY` в `.env`
2. Проверить статус проекта на Supabase Dashboard
3. Проверить RLS политики (если ошибки доступа)

### Проблема: Health monitor не работает

**Решение:**
```bash
# Проверить логи API
docker compose logs api | grep health

# Проверить что health.py доступен
docker compose exec api python -c "from src.monitor.health import check_health"
```

---

## 📊 Post-Launch Monitoring

### Первые 24 часа

**Мониторинг:**
- [ ] Проверять логи каждые 2-3 часа
- [ ] Проверять метрики в Grafana
- [ ] Проверять health endpoint
- [ ] Проверять scheduler.log

**Команды:**
```bash
# Логи
docker compose logs --tail 100 --follow

# Метрики
curl http://localhost:8000/metrics/prometheus | grep reflexio

# Health
watch -n 60 'curl -s http://localhost:8000/health | jq'
```

---

## ✅ Success Criteria

| Критерий | Проверка | Команда |
|----------|----------|---------|
| Контейнеры запущены | Все сервисы `Up` | `docker compose ps` |
| API доступен | Health = `ok` | `curl http://localhost:8000/health` |
| Метрики работают | Prometheus формат | `curl http://localhost:8000/metrics/prometheus` |
| Scheduler активен | Логи пишутся | `tail -f .cursor/logs/scheduler.log` |
| Health monitor | Метрика обновляется | Проверить `metrics.health_status` в Supabase |
| Governance | Метрики в Supabase | `python .cursor/metrics/governance_loop.py --push-metrics` |

---

## 🎯 Final Steps

### 1. Backup Supabase

```bash
bash scripts/backup_supabase.sh
```

**Или вручную:**
1. Supabase Dashboard → Database → Backups
2. Create backup: `reflexio_prod_YYYYMMDD`

### 2. Git Commit

```bash
git add .
git commit -m "Production Level 5 - Autonomous Cycle Verified"
```

### 3. Release Tag

```bash
git tag -a v1.0-production -m "Reflexio 24/7 - Level 5 Autonomous"
git push origin v1.0-production
```

### 4. Мониторинг

Настроить алёрты в Prometheus/Grafana для:
- API down
- High latency
- Low DeepConf confidence
- MCP service failures

---

## 📝 Документация

**Полезные файлы:**
- `DEPLOYMENT.md` — полное руководство по развёртыванию
- `RUNBOOKS.md` — решение инцидентов
- `SECURITY.md` — политика безопасности
- `AUTO_GOVERNANCE_GUIDE.md` — автономное управление
- `PROD_VERIFICATION_REPORT.md` — отчёт готовности
- `AUTONOMOUS_CYCLE_VERIFICATION_REPORT.md` — верификация цикла

---

## ✅ Готовность

После выполнения всех пунктов чеклиста:

**Reflexio 24/7 готов к production!**

Система будет работать полностью автономно:
- ✅ Самонаблюдение (health checks)
- ✅ Самооценка (weekly audit)
- ✅ Самоадаптация (governance loop)
- ✅ Самообучение (metrics & feedback)

---

**Последнее обновление:** 3 ноября 2025  
**Статус:** ✅ Ready for Production Launch

