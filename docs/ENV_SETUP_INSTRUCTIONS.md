# Настройка Environment Variables для Reflexio 24/7

**Инструкция по настройке API ключей и proxy credentials**

---

## 📝 Создание .env файла

Создайте файл `.env` в корне проекта (`D:\24 na 7\.env`):

```bash
# Reflexio 24/7 — Environment Variables
# ВАЖНО: Этот файл содержит конфиденциальные данные
# Убедитесь, что .env в .gitignore!

# ============================================================
# OSINT KDS API Keys
# ============================================================

# Brave Search API Key
BRAVE_API_KEY=your_brave_api_key_here

# Bright Data Proxy (рекомендуется)
# Используется для скрапинга через proxy
BRIGHTDATA_PROXY_HTTP=https://brd-customer-hl_16abad82-zone-tttt:46ju8s7m4bcz@brd.superproxy.io:9515

# Bright Data WebSocket Proxy (опционально)
BRIGHTDATA_PROXY_WS=wss://brd-customer-hl_16abad82-zone-tttt:46ju8s7m4bcz@brd.superproxy.io:9222

# Альтернатива: Bright Data API Key (если нет proxy)
# BRIGHTDATA_API_KEY=your_brightdata_api_key_here

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

# ============================================================
# Другие настройки
# ============================================================

# Logging
LOG_LEVEL=INFO

# API
API_URL=http://localhost:8000
```

---

## ✅ Проверка настройки

После создания `.env` файла выполните:

```bash
python scripts/check_osint_readiness.py
```

Ожидаемый результат:
```
✅ BRAVE_API_KEY найден в .env
✅ BRIGHTDATA_PROXY_HTTP найден в .env
✅ Все модули доступны
✅ Директории созданы
✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!
```

---

## 🔒 Безопасность

**ВАЖНО:**
- ✅ Файл `.env` уже в `.gitignore` — не будет закоммичен
- ⚠️ Не передавайте credentials в открытом виде
- 🔑 Храните `.env` в безопасном месте
- 🚫 Не публикуйте credentials в публичных репозиториях

---

## 🚀 После настройки

После добавления ключей система готова к:

1. **Поиску через Brave Search**
2. **Скрапингу через Bright Data Proxy**
3. **Запуску OSINT миссий**

Запустите первую миссию:
```bash
@playbook osint-mission --mission_file .cursor/osint/missions/first_mission.json
```

---

**Система готова к работе!** 🎯✨




