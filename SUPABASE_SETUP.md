# 🔧 Настройка Supabase для Reflexio 24/7

**Инструкция по интеграции Supabase**

---

## 📋 Что такое Supabase?

**Supabase** — это облачная база данных PostgreSQL с дополнительными сервисами:
- 🗄️ **Database** — PostgreSQL база данных
- 📦 **Storage** — хранилище файлов
- 🔄 **Realtime** — подписки на изменения в реальном времени
- 🔐 **Auth** — аутентификация пользователей

**Простыми словами:** Это как Firebase, но с PostgreSQL под капотом.

---

## 🔑 Данные для подключения

### URL проекта:
```
https://lkmyliwjleegjkcgespp.supabase.co
```

### API ключ (anon/public):
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxrbXlsaXdqbGVlZ2prY2dlc3BwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjIxOTAzNDEsImV4cCI6MjA3Nzc2NjM0MX0._SVPagOjW4uTjZclDk-5HihvlNY6s76wH8vLD5EyRlQ
```

> ⚠️ **Важно:** Это `anon` ключ — безопасен для использования в браузере, если включены RLS (Row Level Security) политики.

---

## 📝 Добавление в .env

Добавьте следующие строки в файл `.env` (в корне проекта):

```bash
# ============================================================
# Supabase Configuration
# ============================================================

# URL проекта Supabase
SUPABASE_URL=https://lkmyliwjleegjkcgespp.supabase.co

# Anon/Public ключ (безопасен для браузера с RLS)
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxrbXlsaXdqbGVlZ2prY2dlc3BwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjIxOTAzNDEsImV4cCI6MjA3Nzc2NjM0MX0._SVPagOjW4uTjZclDk-5HihvlNY6s76wH8vLD5EyRlQ

# Service ключ (опционально, только для серверного использования)
# ВНИМАНИЕ: Service ключ обходит RLS! Используйте только на сервере!
# SUPABASE_SERVICE_KEY=your_service_key_here
```

---

## 🧪 Проверка подключения

### 1. Установка библиотеки (если ещё не установлена)

```bash
pip install supabase
```

### 2. Тест подключения через Python

```bash
python src/storage/supabase_client.py
```

Ожидаемый результат:
```
Status: ok
Message: Supabase API accessible
```

### 3. Проверка через MCP валидатор

```bash
python .cursor/validation/mcp_validator.py --summary
```

Должен показать:
```
[supabase] status: ok, latency_ms: <2000
```

---

## 🎯 Использование в коде

### Базовый пример:

```python
from src.storage.supabase_client import get_supabase_client

# Получаем клиент
client = get_supabase_client()

if client:
    # Пример: чтение из таблицы
    response = client.table("your_table").select("*").limit(10).execute()
    print(response.data)
    
    # Пример: запись данных
    client.table("your_table").insert({
        "column1": "value1",
        "column2": "value2"
    }).execute()
```

### Через настройки:

```python
from src.utils.config import settings

if settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY:
    # Supabase настроен и готов к использованию
    print(f"Supabase URL: {settings.SUPABASE_URL}")
```

---

## 🔒 Безопасность

### Anon Key (публичный ключ)
- ✅ Безопасен для использования в браузере
- ✅ Работает только с включёнными RLS политиками
- ✅ Не может обходить Row Level Security

### Service Key (служебный ключ)
- ⚠️ **ОПАСЕН** для браузера — обходит все RLS политики!
- ✅ Используйте только на сервере
- 🔒 Никогда не коммитьте в Git!

### Рекомендации:
1. Включите RLS для всех таблиц в Supabase Dashboard
2. Настройте политики доступа (Policies)
3. Используйте Service Key только на сервере
4. Храните ключи в `.env` (уже в `.gitignore`)

---

## 📊 Интеграция в проект

### MCP конфигурация

Supabase уже настроен в `.cursor/mcp.json`:

```json
{
  "supabase": {
    "url": "https://lkmyliwjleegjkcgespp.supabase.co",
    "enabled": true,
    "description": "Supabase backend — PostgreSQL база данных и Storage",
    "api_key_env": "SUPABASE_ANON_KEY",
    "capabilities": ["database", "storage", "realtime", "auth"],
    "priority": "high"
  }
}
```

### Миграция с SQLite на Supabase

Согласно `.cursor/mcp.json`:
```json
{
  "database": {
    "type": "sqlite",
    "path": "src/storage/reflexio.db",
    "migrate_to": "supabase"
  }
}
```

Планируется переход с локального SQLite на облачный Supabase для продакшена.

---

## ✅ Чеклист настройки

- [ ] Добавлены `SUPABASE_URL` и `SUPABASE_ANON_KEY` в `.env`
- [ ] Установлена библиотека `supabase` (`pip install supabase`)
- [ ] Проверено подключение через `python src/storage/supabase_client.py`
- [ ] MCP валидатор показывает `status: ok` для Supabase
- [ ] (Опционально) Настроены RLS политики в Supabase Dashboard
- [ ] (Опционально) Создана базовая схема таблиц

---

## 🚀 Следующие шаги

1. **Создать схему базы данных** в Supabase Dashboard
2. **Настроить RLS политики** для безопасности
3. **Создать миграционный скрипт** для переноса данных из SQLite
4. **Обновить код** для использования Supabase вместо SQLite

---

**Готово!** 🎉 Supabase интегрирован в Reflexio 24/7.











