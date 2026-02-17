# ⚡ Quick Start Production — Reflexio 24/7

**Быстрый запуск в продакшене за 5 шагов**

---

## 🚀 Шаг 1: Настройка `.env`

```bash
cp .env.example .env
nano .env  # Заполнить API ключи
```

**Минимум:**
```bash
DB_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_key
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
SAFE_MODE=strict
```

---

## 🔧 Шаг 2: Миграции Supabase

1. Открыть Supabase Dashboard → **SQL Editor**
2. Выполнить `src/storage/migrations/0001_init.sql`
3. Выполнить `src/storage/migrations/0003_rls_policies.sql`

---

## 🐳 Шаг 3: Запуск Docker

```bash
docker compose build
docker compose up -d
```

---

## ✅ Шаг 4: Проверка

```bash
# Статус
docker compose ps

# Health
curl http://localhost:8000/health

# Метрики
curl http://localhost:8000/metrics/prometheus

# Автономный цикл
python scripts/verify_autonomous_cycle.py
```

---

## 📊 Шаг 5: Мониторинг

```bash
# Логи
docker compose logs -f api scheduler

# Grafana (если включён)
open http://localhost:3000
```

---

**Готово!** Reflexio 24/7 работает в production режиме.

**Подробнее:** `PRODUCTION_LAUNCH_CHECKLIST.md`











