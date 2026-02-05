# 🚀 Supabase Migration Guide — Reflexio 24/7

**Полное руководство по миграции с SQLite на Supabase PostgreSQL**

---

## 📋 Предварительные требования

- Supabase проект создан
- `SUPABASE_URL` и `SUPABASE_ANON_KEY` настроены в `.env`
- Доступ к Supabase Dashboard для применения миграций вручную (если CLI недоступен)

---

## 🔧 Шаг 1: Настройка переменных окружения

В `.env`:

```bash
# База данных
DB_BACKEND=supabase

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...  # Anon/public ключ
SUPABASE_SERVICE_ROLE=eyJ...  # Service ключ (опционально, для RLS обхода)
SUPABASE_SCHEMA=public
```

**Проверка подключения:**
```bash
python scripts/test_supabase.py
```

---

## 📝 Шаг 2: Применение схемы базы данных

### Вариант A: Через Supabase Dashboard (рекомендуется)

1. Откройте Supabase Dashboard → **SQL Editor**
2. Скопируйте содержимое `src/storage/migrations/0001_init.sql`
3. Вставьте в SQL Editor и выполните
4. Повторите для `src/storage/migrations/0003_rls_policies.sql`

### Вариант B: Через скрипт (если Supabase CLI установлен)

```bash
python src/storage/migrate.py --to supabase --apply-schema
```

**Примечание:** Скрипт попытается использовать Supabase CLI, если доступен. Иначе выведет инструкции для ручного применения.

---

## 🔄 Шаг 3: Миграция данных

### 3.1 Backup SQLite

```bash
# Автоматический backup через playbook
@playbook db-migrate --target supabase --backup true

# Или вручную
python src/storage/migrate.py --backup
```

### 3.2 Dry Run (проверка)

```bash
@playbook db-migrate --target supabase --dry_run true
```

### 3.3 Реальная миграция

```bash
@playbook db-migrate --target supabase --dry_run false --backup true
```

Или напрямую:
```bash
python src/storage/migrate.py --to supabase --migrate-data --backup
```

---

## ✅ Шаг 4: Проверка миграции

### 4.1 Проверка количества строк

```bash
python src/storage/migrate.py --verify
```

Результат покажет количество строк в SQLite vs Supabase для каждой таблицы.

### 4.2 Проверка доступа

```bash
python - <<'PYCODE'
from src.storage.db import get_db
db = get_db()

# Проверяем доступ к таблицам
tables = ["missions", "claims", "audio_meta", "text_entries", "insights", "metrics"]
for table in tables:
    rows = db.select(table, limit=1)
    print(f"✅ {table}: {len(rows)} row(s)")
PYCODE
```

---

## 🔒 Шаг 5: Настройка RLS (Row-Level Security)

RLS политики уже определены в `src/storage/migrations/0003_rls_policies.sql`.

**Применение:**
1. Откройте Supabase Dashboard → **SQL Editor**
2. Скопируйте содержимое `0003_rls_policies.sql`
3. Выполните SQL

**Проверка:**
1. Откройте Supabase Dashboard → **Table Editor**
2. Выберите таблицу (например, `claims`)
3. Убедитесь что RLS включен (колонка "RLS" = Enabled)

---

## 📊 Новые таблицы

| Таблица | Описание | Ключевые поля |
|---------|----------|---------------|
| `audio_meta` | Метаданные аудио файлов | `id` (UUID), `filename`, `duration` |
| `text_entries` | Текстовые записи с embeddings | `id` (UUID), `mission_id`, `content`, `embedding` |
| `insights` | Инсайты из анализа | `id` (UUID), `title`, `summary`, `confidence` |
| `claims` | Утверждения из OSINT | `id` (UUID), `claim_text`, `confidence`, `validated` |
| `missions` | OSINT миссии | `id` (UUID), `name`, `status`, `parameters` (JSONB) |
| `metrics` | Системные метрики | `id` (SERIAL), `metric_name`, `metric_value` |

---

## 🔄 Обратная миграция (откат)

Если нужно вернуться к SQLite:

```bash
# В .env
DB_BACKEND=sqlite

# Восстановить backup
cp src/storage/reflexio.db.backup.* src/storage/reflexio.db
```

---

## 🐛 Troubleshooting

### Проблема: "Supabase client not available"

**Решение:**
- Проверьте `SUPABASE_URL` и `SUPABASE_ANON_KEY` в `.env`
- Убедитесь что `pip install supabase` выполнен

### Проблема: "RLS policies not applied"

**Решение:**
- Примените `0003_rls_policies.sql` через Supabase Dashboard SQL Editor
- Проверьте что Service Role Key используется для записи (если RLS слишком строгий)

### Проблема: "Migration failed - table already exists"

**Решение:**
- Удалите таблицы в Supabase Dashboard или используйте `DROP TABLE IF EXISTS` перед миграцией
- Или пропустите шаг применения схемы если таблицы уже существуют

### Проблема: "Row count mismatch"

**Решение:**
- Проверьте логи миграции
- Убедитесь что все таблицы были перенесены
- Используйте `--verify` для детальной диагностики

---

## 📝 Отчёт о миграции

После миграции проверьте отчёт:

```bash
cat .cursor/audit/db_migration_report.json
```

Отчёт содержит:
- Статус миграции каждой таблицы
- Количество перенесённых строк
- Ошибки (если есть)

---

## ✅ Критерии успешной миграции

- [x] Все таблицы созданы в Supabase
- [x] RLS политики применены
- [x] Количество строк совпадает (±1 допустимая погрешность)
- [x] API работает с `DB_BACKEND=supabase`
- [x] OSINT миссии сохраняют результаты в Supabase
- [x] `/health` endpoint возвращает 200

---

## 🚀 После миграции

1. **Обновите `DB_BACKEND` в `.env`:**
   ```bash
   DB_BACKEND=supabase
   ```

2. **Перезапустите API:**
   ```bash
   docker compose restart api
   # или
   uvicorn src.api.main:app --reload
   ```

3. **Проверьте работу:**
   ```bash
   curl http://localhost:8000/health
   ```

4. **Запустите тестовую OSINT миссию:**
   ```bash
   @playbook osint-mission --mission_file .cursor/osint/missions/first_mission.json
   ```

5. **Проверьте что результаты сохранены:**
   ```bash
   python - <<'PYCODE'
   from src.storage.db import get_db
   db = get_db()
   missions = db.select("missions", limit=5)
   claims = db.select("claims", limit=5)
   print(f"Missions: {len(missions)}, Claims: {len(claims)}")
   PYCODE
   ```

---

**Последнее обновление:** 3 ноября 2025











