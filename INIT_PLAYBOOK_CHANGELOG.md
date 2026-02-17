# Init Playbook Changelog — Reflexio 24/7

## v1.2 (Production-Ready)

### Новые фичи

1. **Проверка двух миров ключей**
   - Автоматическая проверка Python `.env` + MCP Cursor
   - Использует `scripts/check_api_keys.py`
   - Останавливает инициализацию при ошибках

2. **FFmpeg проверка**
   - Проверка наличия FFmpeg в системе
   - Важно для ASR (Whisper)

3. **Проверка порта**
   - Проверяет доступность порта перед запуском
   - Избегает конфликтов портов

4. **Фоновый запуск API + Health Check**
   - Запускает API в фоне
   - Ожидает готовности `/health` (до 30 секунд)
   - Сохраняет PID для корректной остановки

5. **Валидация MCP**
   - Проверка структуры `.cursor/mcp.json`
   - Опциональный запуск `@playbook validate-mcp`

6. **MCP & Proxy diagnostics**
   - Автоматический запуск диагностики прокси/SERP
   - Если playbooks доступны

7. **Verify Full Pipeline**
   - Запуск `scripts/verify_full_pipeline.py`
   - Проверка всех компонентов конвейера
   - Readiness gates перед завершением

8. **Опциональный Scheduler**
   - Параметр `start_scheduler: true`
   - Запуск планировщика в фоне

9. **Корректная остановка**
   - Останавливает API после инициализации
   - Сохраняет PID для последующего управления

### Улучшения

- Автосоздание `.env` с подсветкой обязательных ключей
- Лучшие сообщения об ошибках
- Структурированное резюме в конце

### Кроссплатформенные скрипты

Созданы отдельные скрипты для управления API:

- `scripts/start_api.sh` / `scripts/start_api.ps1` — запуск API
- `scripts/stop_api.sh` / `scripts/stop_api.ps1` — остановка API

### Параметры

```yaml
skip_database: false      # Пропустить инициализацию БД
skip_audit: false          # Пропустить первый аудит
python_version: "3.11"     # Минимальная версия Python
api_host: "127.0.0.1"     # Хост для API
api_port: "8000"           # Порт для API
start_scheduler: false     # Запустить scheduler после init
```

### Использование

```bash
# Стандартная инициализация
@playbook init-reflexio

# Без аудита
@playbook init-reflexio --skip_audit=true

# С scheduler
@playbook init-reflexio --start_scheduler=true

# Другой порт
@playbook init-reflexio --api_port=8080
```

---

## v1.0 (Original)

Базовая версия с:
- Проверкой Python версии
- Созданием `.env`
- Установкой зависимостей
- Инициализацией БД
- Созданием директорий

---

**Последнее обновление:** 3 ноября 2025











