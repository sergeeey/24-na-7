# 🚀 Локальная настройка Reflexio 24/7

**Минимальная версия для локального тестирования**

---

## 🎯 Цель

Создать рабочую локальную версию Reflexio без зависимости от Supabase, OpenAI и других внешних сервисов.

---

## ⚡ Быстрая настройка (автоматически)

```powershell
# Запустите скрипт из текущего проекта
.\scripts\setup_local_reflexio.ps1

# Или укажите другую папку
.\scripts\setup_local_reflexio.ps1 -TargetPath "C:\MyReflexio"
```

Скрипт автоматически создаст:
- ✅ Структуру директорий
- ✅ `src/api/main.py` — минимальный FastAPI сервер
- ✅ `Dockerfile` — контейнер для API
- ✅ `docker-compose.yml` — оркестрация
- ✅ `requirements.txt` — зависимости
- ✅ `README.md` — инструкции

---

## 📋 Ручная настройка (пошагово)

### Этап 1. Создание папки

```powershell
mkdir C:\Reflexio
cd C:\Reflexio
```

### Этап 2. Структура

```powershell
mkdir src\api
mkdir logs
```

### Этап 3. Файлы

#### `src/api/main.py`

```python
from fastapi import FastAPI
from pydantic import BaseModel
import time

app = FastAPI(title="Reflexio Local")

class HealthResponse(BaseModel):
    status: str
    message: str
    timestamp: float

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        message="Reflexio is healthy",
        timestamp=time.time()
    )

@app.get("/")
def root():
    return {"message": "👋 Reflexio Local API is running!"}
```

#### `Dockerfile`

```dockerfile
FROM python:3.11-slim

RUN pip install fastapi uvicorn

WORKDIR /app
COPY ./src ./src

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### `docker-compose.yml`

```yaml
version: "3.9"

services:
  api:
    build: .
    container_name: reflexio_api
    ports:
      - "8000:8000"
    volumes:
      - ./src:/app/src
      - ./logs:/app/logs
    restart: unless-stopped
```

---

## 🚀 Запуск

### С Docker (рекомендуется)

```powershell
# Сборка и запуск
docker compose up --build

# В фоне
docker compose up -d --build

# Остановка
docker compose down
```

### Без Docker (локально)

```powershell
# Установка зависимостей
pip install fastapi uvicorn

# Запуск
python -m uvicorn src.api.main:app --reload
```

---

## 🌐 Проверка

### В браузере

- **http://localhost:8000/** — корневой эндпоинт
- **http://localhost:8000/health** — health check
- **http://localhost:8000/docs** — Swagger UI (автоматически)

### Через PowerShell

```powershell
# Health check
Invoke-WebRequest http://localhost:8000/health | Select-Object -ExpandProperty Content

# Корневой эндпоинт
Invoke-WebRequest http://localhost:8000/ | Select-Object -ExpandProperty Content
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "message": "Reflexio is healthy",
  "timestamp": 1730682415.123
}
```

---

## 📊 Управление

### Проверка статуса

```powershell
# Список контейнеров
docker ps

# Логи
docker compose logs -f api

# Перезапуск
docker compose restart api
```

### Очистка

```powershell
# Остановка и удаление контейнеров
docker compose down

# Остановка, удаление контейнеров и volumes
docker compose down -v

# Пересборка с нуля
docker compose build --no-cache
```

---

## 🔄 Следующие шаги

### Вариант 1: Оставить локальным

Если хотите простую версию для тестирования:
- ✅ Добавьте новые эндпоинты в `src/api/main.py`
- ✅ Расширьте функциональность
- ✅ Используйте локально для разработки

### Вариант 2: Расширить до полной версии

Если хотите добавить Supabase, OSINT и мониторинг:

1. **Добавить Supabase:**
   ```powershell
   # Создайте .env файл
   echo "SUPABASE_URL=..." > .env
   echo "SUPABASE_ANON_KEY=..." >> .env
   ```

2. **Добавить зависимости:**
   ```powershell
   pip install supabase
   ```

3. **Интегрировать с полным проектом:**
   - Скопируйте модули из `D:\24 na 7\src\`
   - Добавьте конфигурацию из `.cursor/`
   - Запустите `@playbook init-reflexio`

---

## 📁 Структура проекта

```
C:\Reflexio\
├── src/
│   └── api/
│       └── main.py          # FastAPI приложение
├── logs/                     # Логи
├── Dockerfile                # Docker образ
├── docker-compose.yml        # Docker Compose
├── requirements.txt          # Python зависимости
└── README.md                 # Документация
```

---

## ✅ Критерии успеха

После запуска должно быть:

- ✅ API доступен на `http://localhost:8000`
- ✅ `/health` возвращает `{"status": "ok"}`
- ✅ `/` возвращает приветственное сообщение
- ✅ Swagger UI доступен на `/docs`
- ✅ Контейнер `reflexio_api` запущен

---

## 🔍 Диагностика проблем

### Проблема: "Port 8000 is already in use"

**Решение:**
```powershell
# Измените порт в docker-compose.yml
ports:
  - "8001:8000"  # Внешний порт: внутренний порт
```

### Проблема: "Docker build failed"

**Решение:**
```powershell
# Пересоберите с очисткой кэша
docker compose build --no-cache
```

### Проблема: "Module not found"

**Решение:**
```powershell
# Проверьте структуру файлов
tree src /F

# Убедитесь, что файл main.py в правильной директории
```

---

**Последнее обновление:** 3 ноября 2025  
**Версия:** 1.0 (Local)  
**Статус:** ✅ Минимальная рабочая версия











