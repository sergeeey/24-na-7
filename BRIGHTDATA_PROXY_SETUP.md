# Bright Data Proxy Setup

**Настройка Bright Data через proxy endpoints**

---

## 🔑 Добавление Proxy Credentials в .env

Откройте файл `.env` в корне проекта и добавьте:

```bash
# Bright Data Proxy (API SERP)
# HTTP Proxy для скрапинга
BRIGHTDATA_PROXY_HTTP=https://brd-customer-hl_16abad82-zone-tttt:46ju8s7m4bcz@brd.superproxy.io:9515

# WebSocket Proxy (для будущего использования)
BRIGHTDATA_PROXY_WS=wss://brd-customer-hl_16abad82-zone-tttt:46ju8s7m4bcz@brd.superproxy.io:9222
```

---

## ⚙️ Как это работает

### Через Proxy (рекомендуется)

Если установлен `BRIGHTDATA_PROXY_HTTP`, клиент будет использовать proxy для всех запросов:

```python
from src.mcp.clients import get_bright_client

# Автоматически использует proxy из .env
bright = get_bright_client()

# Извлечение контента через proxy
html = bright.scrape_page("https://example.com")
markdown = bright.scrape_markdown("https://example.com")
```

### Через API Key (альтернатива)

Если proxy не установлен, используется API key:

```bash
BRIGHTDATA_API_KEY=your_api_key_here
```

---

## 🧪 Проверка работы

### Тест 1: Проверка готовности

```bash
python scripts/check_osint_readiness.py
```

Должно показать:
```
✅ BRIGHTDATA_PROXY_HTTP найден в .env
```

### Тест 2: Прямой тест клиента

```python
from src.mcp.clients import get_bright_client

try:
    bright = get_bright_client()
    content = bright.scrape_markdown("https://example.com")
    print(f"✅ Bright Data работает! Получено {len(content or '')} символов")
except Exception as e:
    print(f"❌ Ошибка: {e}")
```

### Тест 3: Через OSINT миссию

```bash
@playbook osint-mission --mission_file .cursor/osint/missions/first_mission.json
```

---

## 📊 Формат Proxy URL

Bright Data proxy URL имеет формат:

```
https://brd-customer-USERNAME-zone-ZONE:PASSWORD@brd.superproxy.io:PORT
```

Где:
- `USERNAME` — ваш customer ID
- `ZONE` — название zone (например, `tttt`)
- `PASSWORD` — пароль для доступа
- `PORT` — порт (обычно 9515 для HTTP, 9222 для WebSocket)

---

## 🔒 Безопасность

⚠️ **ВАЖНО:**
- Proxy credentials содержат пароль в открытом виде
- Файл `.env` должен быть в `.gitignore`
- Не коммитьте `.env` в Git
- Не передавайте credentials в открытом виде

---

## ✅ После настройки

После добавления proxy credentials:

1. ✅ Bright Data будет использовать proxy для всех запросов
2. ✅ Система сможет обходить блокировки и CAPTCHA
3. ✅ OSINT миссии будут работать через proxy автоматически
4. ✅ Контент будет извлекаться через Bright Data proxy

---

**Система готова к использованию Bright Data через proxy!** 🚀













