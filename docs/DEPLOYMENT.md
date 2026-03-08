# 🚀 Deployment Guide — Reflexio 24/7

**Руководство по развёртыванию в продакшен**

---

## 📋 Требования

- Docker & Docker Compose
- Git
- Минимум 2GB RAM, 10GB disk
- Доступ к интернету (для LLM, MCP)
- **FFmpeg** (включён в Dockerfile.api, но нужен для локального запуска)

---

## 🔧 Подготовка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd reflexio-24-7
```

### 2. Установка FFmpeg (для локального запуска)

**FFmpeg необходим для ASR (Whisper) и обработки аудио.**

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg
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

**Примечание:** FFmpeg **уже включён в Dockerfile.api**, поэтому для Docker установка не требуется.

### 3. Настройка переменных окружения

```bash
# Скопировать шаблон
cp .env.example .env

# Редактировать .env
nano .env
```

**Минимальный набор переменных:**

```bash
# LLM
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
# ИЛИ
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-...

# Database
DB_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE=eyJ...  # Только для сервера!

# Security
SAFE_MODE=strict
SAFE_PII_MASK=1

# MCP (опционально)
BRAVE_API_KEY=...
BRIGHTDATA_API_KEY=...
BRIGHTDATA_PROXY_HTTP=...
```

### 3. Проверка готовности

```bash
# Проверка всех компонентов
@playbook prod-readiness
```

---

## 🐳 Docker Deployment

### Быстрый старт

```bash
# 1. Сборка образов
docker compose build

# 2. Запуск всех сервисов
docker compose up -d

# 3. Проверка статуса
docker compose ps

# 4. Проверка health
curl http://localhost:8000/health

# 5. Проверка метрик
curl http://localhost:8000/metrics/prometheus
```

**Ожидаемые сервисы:**
- `reflexio-api` — основной API сервер
- `reflexio-worker` — worker процессы (OSINT, обработка)
- `reflexio-scheduler` — планировщик автономных задач
- `reflexio-prometheus` — метрики (опционально, profile `observability`)
- `reflexio-grafana` — дашборды (опционально, profile `observability`)

### Production deployment

```bash
# 1. Применить миграции Supabase (если ещё не применены)
# См. шаг 4 выше

# 2. Сборка образов
docker compose build

# 3. Проверка образов
docker images | grep reflexio

# 4. Запуск в фоне
docker compose up -d

# 5. Проверка статуса всех сервисов
docker compose ps

# 6. Проверка логов
docker compose logs -f api scheduler worker

# 7. Проверка health
curl http://localhost:8000/health

# 8. Проверка автономного цикла
python scripts/verify_autonomous_cycle.py
```

### Проверка автономного цикла

После запуска убедитесь, что автономный цикл работает:

```bash
# 1. Проверка scheduler
docker compose logs scheduler | tail -20

# 2. Проверка health monitor
curl http://localhost:8000/health

# 3. Проверка метрик в Supabase
python .cursor/metrics/governance_loop.py --push-metrics

# 4. Полная верификация
python scripts/verify_autonomous_cycle.py
```

---

## 🔄 Миграция базы данных

### Supabase — основной storage

**Reflexio 24/7** использует **Supabase PostgreSQL** как основной storage для production.

**Преимущества:**
- Облачное хранилище с автоматическим backup
- Row-Level Security (RLS) для безопасности
- JSONB для гибкого хранения (parameters, metadata)
- UUID для распределённых систем
- Real-time subscriptions (опционально)

### SQLite → Supabase

```bash
# 1. Dry run (проверка без реальной миграции)
@playbook db-migrate --to supabase --dry-run

# 2. Backup SQLite
cp src/storage/reflexio.db src/storage/reflexio.db.backup.$(date +%Y%m%d)

# 3. Миграция
@playbook db-migrate --to supabase

# 4. Проверка
python - <<'PYCODE'
from src.storage.db import get_db_backend
backend = get_db_backend()
print(f"Backend: {type(backend).__name__}")
print(f"Transcriptions: {len(backend.select('transcriptions', limit=10))}")
PYCODE
```

---

## 📊 Observability Stack

### Запуск Prometheus + Grafana

```bash
# Запуск с observability профилем
docker compose --profile observability up -d prometheus grafana

# Доступ:
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3000 (admin / admin)
```

### Настройка Grafana

1. Добавить Prometheus data source: `http://prometheus:9090`
2. Импортировать dashboard: `observability/grafana_dashboards/reflexio.json`

---

## 🔄 CI/CD (GitHub Actions)

### Настройка

1. **Secrets в GitHub:**
   - `DEPLOY_HOST` — IP сервера
   - `DEPLOY_USER` — SSH пользователь
   - `DEPLOY_SSH_KEY` — SSH приватный ключ

2. **Автоматический деплой:**
   - Push в `main` → автоматический deploy на staging
   - Tag `v*` → автоматический deploy на production

### Ручной deploy

```bash
# На сервере
cd /opt/reflexio
git pull origin main
docker compose pull
docker compose up -d --build
docker compose exec api python -c "import requests; requests.get('http://localhost:8000/health')"
```

### Обновление Caddy на VPS (исправление 404 для reflexio247.duckdns.org)

Если приложение показывает «сервер 404», обновите Caddyfile на сервере (в нём должны быть оба домена: `reflexio.duckdns.org` и `reflexio247.duckdns.org`).

**С ПК (PowerShell, Windows):**
```powershell
cd "D:\24 na 7"
$env:REFLEXIO_SERVER = "root@reflexio247.duckdns.org"   # или root@IP_СЕРВЕРА
.\scripts\update_caddy_on_server.ps1
```

**С ПК (Bash / WSL / Linux):**
```bash
cd /path/to/project
export REFLEXIO_SERVER=root@reflexio247.duckdns.org
./scripts/update_caddy_on_server.sh
```

Требуется SSH-доступ к серверу (ключ или пароль).

---

## 🌍 Альтернативные платформы

### Render.com

```yaml
# render.yaml
services:
  - type: web
    name: reflexio-api
    env: docker
    dockerfilePath: ./Dockerfile.api
    envVars:
      - key: OPENAI_API_KEY
        sync: false
```

### Fly.io

```bash
# fly.toml
fly launch --dockerfile Dockerfile.api
fly secrets set OPENAI_API_KEY=...
fly deploy
```

---

## 🔍 Мониторинг после деплоя

### Первые 24 часа

```bash
# Проверка каждые 30 минут
watch -n 1800 'curl http://localhost:8000/health && @playbook validate-mcp'
```

### Метрики для отслеживания

- Health check: `/health` → должен возвращать 200
- Latency: P95 < 5 сек
- Error rate: < 1%
- DeepConf confidence: > 0.8

---

## 🚨 Troubleshooting

### Проблема: Контейнер не запускается

```bash
# Проверка логов
docker compose logs api

# Проверка конфигурации
docker compose config

# Пересборка
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Проблема: База данных недоступна

```bash
# Fallback на SQLite
DB_BACKEND=sqlite docker compose up -d

# Или проверка Supabase
python src/storage/supabase_client.py
```

---

## ⏱ Чеклист: приложение и сервер работают «как часики»

Если приложение на телефоне показывает 404 или «сервер недоступен», пройди по шагам ниже.

### 1. Сервер (VPS)

- **Код:** на VPS задеплоена актуальная версия бэкенда (с маршрутом `GET /ingest/pipeline-status` и async ingest).
- **Caddy:** в Caddyfile должны быть оба домена: `reflexio.duckdns.org` и `reflexio247.duckdns.org`. Применить:
  ```powershell
  $env:REFLEXIO_SERVER = "root@reflexio247.duckdns.org"
  .\scripts\update_caddy_on_server.ps1
  ```
  При первом SSH ввести `yes` при запросе ключа.
- **Проверка:**  
  `curl -s -o /dev/null -w "%{http_code}" https://reflexio247.duckdns.org/health` → 200.  
  С заголовцем Authorization (если требуется):  
  `curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer YOUR_KEY" https://reflexio247.duckdns.org/ingest/pipeline-status` → 200.

### 2. Телефон

- Установить последнюю сборку: из корня проекта `cd android && .\gradlew installDebug` (устройство по USB) или скрипт из `scripts/`.
- В настройках приложения: URL сервера = `https://reflexio247.duckdns.org`, указан API key (PROD_API_KEY в `local.properties` при сборке).
- Открыть приложение → полоска пайплайна: после «Проверить» или после отправки записи статус «сервер» должен стать зелёным.

### 3. Проверка цикла

- Сделать одну тестовую запись, дождаться этапа «received» и обработки.
- В «Итог дня» или «Спроси» должны появиться данные (если есть записи за сегодня и бэкенд пишет в ту же БД).

---

## 📝 Post-Deployment Checklist

### Обязательные проверки

- [ ] Health check возвращает 200: `curl http://localhost:8000/health`
- [ ] Метрики доступны: `curl http://localhost:8000/metrics/prometheus`
- [ ] Все контейнеры запущены: `docker compose ps`
- [ ] Scheduler работает: `docker compose logs scheduler | tail -20`
- [ ] Health monitor активен: проверка `metrics.health_status` в Supabase

### Опциональные проверки

- [ ] MCP сервисы работают: `@playbook validate-mcp`
- [ ] LLM smoke test проходит: `python scripts/smoke_llm.py`
- [ ] Grafana dashboard показывает данные (если включён profile `observability`)
- [ ] Алёрты настроены и работают
- [ ] Backup БД настроен (Supabase Dashboard → Backups)
- [ ] Логи ротируются (Docker logging driver)

### Автономный цикл

- [ ] Scheduler логирует задачи: `.cursor/logs/scheduler.log`
- [ ] Health monitor обновляет метрики каждые 5 минут
- [ ] Governance метрики в Supabase: `ai_reliability`, `context_hit_rate`
- [ ] Hooks реагируют на события
- [ ] Weekly audit запускается автоматически

**Проверка:**
```bash
python scripts/verify_autonomous_cycle.py
```

---

**Последнее обновление:** 3 ноября 2025

