# ✅ Чеклист верификации — Reflexio 24/7

**Быстрая проверка всех компонентов после настройки.**

---

## 🎯 Цель

Убедиться, что «два мира ключей» настроены правильно и всё работает.

---

## 📋 Пошаговая проверка

### 1️⃣ Заполнить `.env` (Мир Python/Backend)

**Расположение:** Корень проекта (рядом с `README.md`)

```bash
# Бэкенд/БД/LLM
DB_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=...
OPENAI_API_KEY=...          # или ANTHROPIC_API_KEY=...
LOG_LEVEL=INFO

# (опционально) Brave/BD для кода Python, если используешь их вне MCP
BRAVE_API_KEY=...
BRIGHTDATA_API_KEY=...
BRIGHTDATA_PROXY_HTTP=...
BRIGHTDATA_PROXY_WS=...
```

**✅ Проверка:**
```bash
python -c "from src.utils.config import settings; print('✅ .env loaded' if settings.SUPABASE_URL else '❌ .env not loaded')"
```

---

### 2️⃣ Добавить ключи в Cursor → Settings → MCP (Мир MCP)

**Важно:** MCP серверы Cursor **НЕ читают `.env` проекта!**

1. Открыть Cursor → **Settings** → **Features → MCP → Configure**
2. Для каждого сервера:
   - **brave**: `BRAVE_API_KEY`
   - **brightdata**: `BRIGHTDATA_API_KEY` (или прокси: `BRIGHTDATA_PROXY_HTTP`, `BRIGHTDATA_PROXY_WS`)
3. Нажать **Save**
4. Выполнить **Developer: Reload Window** (`Cmd/Ctrl + Shift + P`)

**✅ Проверка:**
- Серверы **зелёные** в списке MCP
- Нет ошибок в `View → Output → MCP Logs`

---

### 3️⃣ Быстрая проверка ключей

```bash
python scripts/check_api_keys.py
```

**Ожидаемый результат:**
- ✅ найден `.env` и считаны нужные переменные
- ✅ MCP-конфиг валиден
- ⚠️ может быть предупреждение про отсутствующие MCP ключи (если не настроены в Cursor Settings)

**Если есть ошибки:** см. `API_KEYS_SETUP.md`

---

### 4️⃣ Диагностика доступа

#### MCP конфигурация:
```bash
@playbook validate-mcp-config
@playbook validate-mcp
```

**Отчёты:**
- `.cursor/audit/mcp_config_validation.md`
- `.cursor/audit/mcp_health.json`

#### Прокси/серпы:
```bash
@playbook proxy-diagnostics
@playbook serp-diagnostics
```

**Отчёты:**
- `.cursor/audit/proxy_diagnostics.md`
- `.cursor/audit/serp_diagnostics.md`

---

### 5️⃣ Контрольный прогон конвейера

#### OSINT готовность:
```bash
python scripts/check_osint_readiness.py
```

#### Первая OSINT миссия:
```bash
@playbook osint-mission --mission_file .cursor/osint/missions/first_mission.json
```

**Проверить артефакты:**
- ✅ `.cursor/osint/results/*.json`
- ✅ `.cursor/memory/osint_research.md`
- ✅ записи в таблицах `missions`, `claims` (Supabase)

**Проверка в Supabase:**
```sql
SELECT * FROM missions ORDER BY created_at DESC LIMIT 5;
SELECT * FROM claims ORDER BY created_at DESC LIMIT 5;
```

---

### 6️⃣ Проверка API endpoints

```bash
# Health
curl http://localhost:8000/health

# Metrics
curl http://localhost:8000/metrics/prometheus
```

**Ожидаемый результат:**
- Health: `{"status": "ok", ...}`
- Metrics: Prometheus формат с метриками

---

### 7️⃣ Полная проверка конвейера

```bash
python scripts/verify_full_pipeline.py
```

**Отчёт:** `.cursor/audit/full_pipeline_verification.json`

---

## 🛡️ Встроенный контроль

### Предзапусковой плейбук

**`prod-readiness.yaml`** теперь включает проверку API ключей:
- ✅ Проверка обоих «миров» ключей
- ✅ Валидация конфигурации
- ✅ Автоматическая диагностика

**Запуск:**
```bash
@playbook prod-readiness
```

---

### Docker: автоматическая загрузка `.env`

**`docker-compose.yml`** обновлён:
- ✅ `env_file: .env` для всех сервисов (`api`, `worker`, `scheduler`)
- ✅ Автоматическая загрузка всех переменных из `.env`

**После изменения `.env`:**
```bash
docker compose up -d --build
```

---

## 🚨 Частые причины проблем

### ❌ "Cursor ничего не сделал"

1. **Ключи только в `.env`, но не в Settings → MCP**
   - ✅ Решение: Настроить в Cursor Settings → MCP

2. **Не перезагружено окно редактора**
   - ✅ Решение: `Developer: Reload Window`

3. **Опечатка в имени переменной**
   - ✅ Решение: Проверить точное совпадение: `BRIGHTDATA_API_KEY` (не `BRIGHT_DATA_API_KEY`)

4. **Прокси Bright Data без полного URL**
   - ✅ Решение: Нужен полный URL: `https://brd-customer-<id>-zone-<zone>:<pass>@brd.superproxy.io:9515`

5. **Docker не видит ключей**
   - ✅ Решение: Проверить `env_file: .env` в `docker-compose.yml` и пересобрать: `docker compose up -d --build`

6. **CRLF/кодировка `.env` (Windows)**
   - ✅ Решение: Сохранить в UTF-8 без BOM, переводы строк LF

---

## ✅ Критерии успеха

После всех шагов должно быть:

- ✅ `python scripts/check_api_keys.py` → **OK** для обоих миров
- ✅ `@playbook validate-mcp` → все MCP **healthy**
- ✅ `@playbook proxy-diagnostics` / `serp-diagnostics` → отчёты без ошибок
- ✅ Первая OSINT-миссия даёт результаты и пишет в Supabase
- ✅ `/health` = 200
- ✅ `/metrics/prometheus` отдаёт метрики

---

## 🔍 Быстрая диагностика

**Если что-то не работает:**

1. **Проверка Python `.env`:**
   ```bash
   python -c "from src.utils.config import settings; import json; print(json.dumps(settings.model_dump(), indent=2, ensure_ascii=False))"
   ```

2. **Проверка MCP логов:**
   - В Cursor: `View → Output → MCP`
   - Ищи ошибки: `missing API key`, `authentication failed`

3. **Полная проверка:**
   ```bash
   python scripts/verify_full_pipeline.py
   ```

---

## 📚 Документация

- **API_KEYS_SETUP.md** — подробная инструкция по настройке ключей
- **PRODUCTION_LAUNCH_CHECKLIST.md** — полный чеклист запуска
- **DEPLOYMENT.md** — руководство по развёртыванию

---

**Последнее обновление:** 3 ноября 2025  
**Статус:** ✅ Ready for Verification











