# 🚀 First Launch Guide — Reflexio 24/7

**Полная инструкция по первому запуску системы с нуля**

---

## 📋 Что делает First Launch

Скрипт `first_launch.sh` / `first_launch.ps1` объединяет все шаги инициализации:

1. ✅ Проверка окружения (Python, Git, Docker)
2. ✅ Инициализация через `@playbook init-reflexio`
3. ✅ Проверка API ключей (два мира)
4. ✅ Полная проверка конвейера (`verify_full_pipeline.py`)
5. ✅ Запуск Docker контейнеров (опционально)

---

## 🚀 Быстрый старт

### 0. Финальная проверка (рекомендуется)

```bash
# Linux/macOS
chmod +x scripts/final_verification.sh
./scripts/final_verification.sh

# Windows PowerShell
.\scripts\final_verification.ps1
```

### 1. Запуск системы

**Linux/macOS:**
```bash
chmod +x scripts/first_launch.sh
./scripts/first_launch.sh
```

**Windows PowerShell:**
```powershell
.\scripts\first_launch.ps1
```

---

## ⚙️ Параметры

### Linux/macOS

```bash
# Пропустить Docker
SKIP_DOCKER=true ./scripts/first_launch.sh

# Пропустить аудит
SKIP_AUDIT=true ./scripts/first_launch.sh

# Запустить scheduler
START_SCHEDULER=true ./scripts/first_launch.sh

# Все параметры сразу
SKIP_AUDIT=true START_SCHEDULER=true ./scripts/first_launch.sh
```

### Windows PowerShell

```powershell
# Пропустить Docker
.\scripts\first_launch.ps1 -SkipDocker

# Пропустить аудит
.\scripts\first_launch.ps1 -SkipAudit

# Запустить scheduler
.\scripts\first_launch.ps1 -StartScheduler

# Все параметры сразу
.\scripts\first_launch.ps1 -SkipAudit -StartScheduler
```

---

## 📊 Что проверяется

| Этап | Проверка | Результат |
|------|----------|-----------|
| **Окружение** | Python версия, Git, Docker | ✅ или ❌ |
| **Init Playbook** | FFmpeg, ключи, MCP, Health | ✅ или предупреждения |
| **API Keys** | Python .env + MCP Cursor | ✅ или ⚠️ |
| **Full Pipeline** | Все компоненты конвейера | ✅ или ⚠️ |
| **Docker** | Сборка и запуск контейнеров | ✅ или ⚠️ |

---

## 📁 Отчёты

После выполнения скрипт создаёт отчёты в `.cursor/audit/`:

- `api_keys_check.json` — проверка ключей
- `full_pipeline_verification.json` — проверка конвейера
- `prod_readiness_report.json` — готовность к продакшену

---

## 🎯 Сценарии использования

### 1. Первый запуск на чистом сервере

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd reflexio-24-7

# 2. Создать виртуальное окружение (опционально)
python -m venv .venv
source .venv/bin/activate  # или .venv\Scripts\activate на Windows

# 3. Установить зависимости
pip install -e ".[dev]"

# 4. Запустить first_launch
./scripts/first_launch.sh
```

**Ожидаемый результат:**
- ✅ Все проверки пройдены
- ✅ Docker контейнеры запущены
- ✅ API доступен на `http://localhost:8000`

---

### 2. Локальная разработка (без Docker)

```bash
SKIP_DOCKER=true ./scripts/first_launch.sh
```

**Ожидаемый результат:**
- ✅ Инициализация завершена
- ✅ API ключи проверены
- ✅ Конвейер проверен
- ⏭️ Docker пропущен

---

### 3. Быстрая проверка (без аудита)

```bash
SKIP_AUDIT=true ./scripts/first_launch.sh
```

**Ожидаемый результат:**
- ✅ Все проверки кроме аудита
- ⏭️ Первый аудит пропущен

---

### 4. Production deployment

```bash
# Запустить с scheduler
START_SCHEDULER=true ./scripts/first_launch.sh

# Проверить автономный цикл
python scripts/verify_autonomous_cycle.py
```

**Ожидаемый результат:**
- ✅ Scheduler запущен
- ✅ Автономный цикл работает
- ✅ Все метрики в Supabase

---

## 🔍 Диагностика проблем

### Проблема: "Python не найден"

**Решение:**
```bash
# Проверить Python
python --version

# Если не установлен, установить:
# Linux: sudo apt install python3.11
# macOS: brew install python@3.11
```

---

### Проблема: "API ключи не настроены"

**Решение:**
1. Создать `.env` файл в корне проекта
2. Добавить ключи (см. `API_KEYS_SETUP.md`)
3. Настроить MCP ключи в Cursor Settings
4. Перезапустить проверку

---

### Проблема: "Docker не найден"

**Решение:**
```bash
# Установить Docker
# Linux: https://docs.docker.com/get-docker/
# macOS: https://docs.docker.com/desktop/mac/install/
# Windows: https://docs.docker.com/desktop/windows/install/

# Или пропустить Docker:
SKIP_DOCKER=true ./scripts/first_launch.sh
```

---

### Проблема: "API не отвечает"

**Решение:**
```bash
# Проверить логи
docker compose logs api

# Проверить порт
netstat -an | grep 8000  # Linux
lsof -i :8000            # macOS

# Перезапустить
docker compose restart api
```

---

## ✅ Критерии успеха

После выполнения `first_launch.sh` должно быть:

- ✅ Python 3.11+ установлен
- ✅ FFmpeg доступен
- ✅ `.env` создан и заполнен
- ✅ API ключи проверены (оба мира)
- ✅ MCP конфигурация валидна
- ✅ Конвейер проверен
- ✅ Docker контейнеры запущены (если не пропущен)
- ✅ API доступен на `http://localhost:8000/health`

---

## 📚 Дополнительная документация

- **API_KEYS_SETUP.md** — подробная инструкция по настройке ключей
- **PRODUCTION_LAUNCH_CHECKLIST.md** — полный чеклист запуска
- **VERIFICATION_CHECKLIST.md** — проверка компонентов
- **INIT_PLAYBOOK_CHANGELOG.md** — изменения в init playbook

---

## 🎉 После успешного запуска

```bash
# 1. Проверить health
curl http://localhost:8000/health

# 2. Проверить метрики
curl http://localhost:8000/metrics/prometheus

# 3. Запустить первую OSINT миссию
@playbook osint-mission --mission_file .cursor/osint/missions/first_mission.json

# 4. Проверить автономный цикл
python scripts/verify_autonomous_cycle.py
```

---

**Последнее обновление:** 3 ноября 2025  
**Версия:** 1.0  
**Статус:** ✅ Production-Ready

