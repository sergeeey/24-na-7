# 🚨 Runbooks — Инциденты и восстановление

**Руководство по решению инцидентов в Reflexio 24/7**

---

## 📋 Быстрая диагностика

### 1. Проверка статуса системы

```bash
# Health check
curl http://localhost:8000/health

# Метрики
curl http://localhost:8000/metrics

# Проверка MCP
@playbook validate-mcp

# Проверка безопасности
@playbook security-validate
```

---

## 🔥 Критические инциденты

### Инцидент 1: API недоступен (/health down)

**Симптомы:**
- `curl http://localhost:8000/health` возвращает ошибку
- Контейнер не отвечает

**Диагностика:**
```bash
# Проверка контейнера
docker ps | grep reflexio-api
docker logs reflexio-api --tail 100

# Проверка порта
netstat -an | grep 8000
```

**Решение:**
1. Перезапуск API:
   ```bash
   docker compose restart api
   ```

2. Если не помогает — полный перезапуск:
   ```bash
   docker compose down
   docker compose up -d api
   ```

3. Проверка логов:
   ```bash
   docker logs reflexio-api -f
   ```

**Роллбэк:**
```bash
git restore --source=origin/main .
docker compose down
docker compose up -d --build
```

---

### Инцидент 2: MCP сервисы недоступны

**Симптомы:**
- `@playbook validate-mcp` показывает failed services
- OSINT миссии не выполняются

**Диагностика:**
```bash
python .cursor/validation/mcp_validator.py --summary
cat .cursor/metrics/mcp_health.json
```

**Решение:**
1. **Brave Search недоступен:**
   - Проверить `BRAVE_API_KEY` в `.env`
   - Проверить баланс/лимиты API
   - Выполнить: `@playbook validate-mcp`

2. **Bright Data недоступен:**
   - Проверить proxy credentials
   - Выполнить: `@playbook proxy-diagnostics`
   - Ротация зон: `python src/osint/zone_manager.py --rotate`

3. **Supabase недоступен:**
   - Проверить `SUPABASE_URL` и `SUPABASE_ANON_KEY`
   - Проверить статус Supabase Dashboard
   - Fallback на SQLite: `DB_BACKEND=sqlite`

---

### Инцидент 3: LLM quota exceeded / ошибки API

**Симптомы:**
- `python scripts/smoke_llm.py` возвращает ошибки
- OSINT миссии падают с ошибками LLM

**Диагностика:**
```bash
python scripts/smoke_llm.py
cat .cursor/audit/llm_smoke.json
```

**Решение:**
1. **OpenAI quota exceeded:**
   - Проверить баланс на platform.openai.com
   - Переключиться на другую модель: `LLM_MODEL_ACTOR=gpt-4o-mini`
   - Использовать Anthropic: `LLM_PROVIDER=anthropic`

2. **Anthropic quota exceeded:**
   - Переключиться на OpenAI: `LLM_PROVIDER=openai`

3. **Временные ошибки:**
   - Система автоматически retry (экспоненциальный backoff)
   - Проверить логи: `docker logs reflexio-worker`

**Fallback:**
Система автоматически использует эвристику если LLM недоступен (см. `src/osint/deepconf.py`)

---

### Инцидент 4: База данных недоступна

**Симптомы:**
- Ошибки при записи/чтении данных
- API возвращает 500 на `/metrics`

**Диагностика:**
```bash
# Проверка SQLite
ls -lh src/storage/reflexio.db
sqlite3 src/storage/reflexio.db "SELECT COUNT(*) FROM transcriptions;"

# Проверка Supabase
python src/storage/supabase_client.py
```

**Решение:**
1. **SQLite недоступен:**
   - Проверить права доступа: `chmod 664 src/storage/reflexio.db`
   - Восстановить из backup: `cp src/storage/reflexio.db.backup.* src/storage/reflexio.db`

2. **Supabase недоступен:**
   - Проверить статус на status.supabase.com
   - Переключиться на SQLite: `DB_BACKEND=sqlite`
   - Проверить RLS политики в Supabase Dashboard

**Миграция данных:**
```bash
# Backup перед миграцией
cp src/storage/reflexio.db src/storage/reflexio.db.backup.$(date +%Y%m%d)

# Миграция
@playbook db-migrate --to supabase --dry-run  # Сначала dry-run
@playbook db-migrate --to supabase
```

**Откат миграции:**
```bash
# Если миграция прошла неудачно
DB_BACKEND=sqlite
# Восстановить из backup
```

---

### Инцидент 5: DeepConf confidence < 0.8

**Симптомы:**
- `cursor-metrics.json` показывает `avg_deepconf_confidence < 0.8`
- Уведомления о низкой уверенности

**Автоматическое решение:**
Система автоматически запускает миссию обновления через hook `on_low_confidence`.

**Ручное решение:**
```bash
# Запуск обратной связи DeepConf
python src/osint/deepconf_feedback.py --trigger-auto-mission

# Или запуск новой OSINT миссии
@playbook osint-mission --mission_file .cursor/osint/missions/first_mission.json
```

---

## 🔧 Техническое обслуживание

### Ежедневные проверки

```bash
# 1. Проверка здоровья системы
@playbook validate-mcp
curl http://localhost:8000/health

# 2. Проверка метрик
curl http://localhost:8000/metrics | jq

# 3. Проверка логов на ошибки
docker logs reflexio-api --since 24h | grep -i error
docker logs reflexio-worker --since 24h | grep -i error

# 4. Проверка места на диске
df -h
du -sh src/storage/*
```

### Еженедельные проверки

```bash
# Полный аудит
@playbook audit-standard

# Проверка безопасности
@playbook security-validate

# Проверка готовности к продакшену
@playbook prod-readiness
```

---

## 📊 Мониторинг и алёрты

### Prometheus алёрты

Алёрты настроены в `observability/alert_rules.yml`:

- **ReflexioAPIDown** — API недоступен > 2 мин
- **LLMErrorRateHigh** — ошибки LLM > 2%
- **DeepConfLowConfidence** — confidence < 0.8 > 10 мин
- **MCPServiceDown** — MCP сервис недоступен > 5 мин
- **HighLatency** — P95 latency > 5 сек

### Grafana Dashboard

```bash
# Доступ к Grafana
open http://localhost:3000
# Login: admin / admin (или GRAFANA_PASSWORD из .env)
```

---

## 🚑 Аварийное восстановление

### Полный откат системы

```bash
# 1. Остановить все сервисы
docker compose down

# 2. Восстановить код из Git
git restore --source=origin/main .

# 3. Восстановить БД из backup
cp src/storage/reflexio.db.backup.* src/storage/reflexio.db

# 4. Перезапустить
docker compose up -d --build

# 5. Проверить
curl http://localhost:8000/health
```

### Частичный откат (отдельный компонент)

```bash
# Откат только API
docker compose restart api

# Откат только Worker
docker compose restart worker

# Откат БД (SQLite)
cp src/storage/reflexio.db.backup.* src/storage/reflexio.db
```

---

## 📞 Эскалация

Если проблема не решается:

1. Проверить логи: `docker logs <service> -f`
2. Проверить метрики: Grafana Dashboard
3. Проверить документацию: `SECURITY.md`, `DEPLOYMENT.md`
4. Создать issue в репозитории с:
   - Описанием проблемы
   - Логами (`docker logs`)
   - Результатами диагностики (`@playbook validate-mcp`, etc.)

---

**Последнее обновление:** 3 ноября 2025











