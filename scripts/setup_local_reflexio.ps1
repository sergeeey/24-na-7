#Requires -Version 5.1
# 🚀 Настройка локальной версии Reflexio 24/7
# Создаёт минимальную рабочую версию для тестирования

# Параметры ДОЛЖНЫ быть в самом начале
param(
    [string]$TargetPath = "C:\Reflexio"
)

# Установка UTF-8 кодировки
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "🚀 Настройка локальной версии Reflexio 24/7" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Host "📁 Создание структуры в: $TargetPath" -ForegroundColor Blue

# Создаём директории
$directories = @(
    "$TargetPath\src\api",
    "$TargetPath\logs"
)

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "✅ Создана директория: $dir" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Директория уже существует: $dir" -ForegroundColor Yellow
    }
}

# Файл 1: src/api/main.py
$mainPy = @'
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
'@

$mainPyPath = "$TargetPath\src\api\main.py"
[System.IO.File]::WriteAllText($mainPyPath, $mainPy, [System.Text.Encoding]::UTF8)
Write-Host "✅ Создан файл: $mainPyPath" -ForegroundColor Green

# Файл 2: Dockerfile
$dockerfile = @'
# Базовый образ Python
FROM python:3.11-slim

# Установка зависимостей
RUN pip install fastapi uvicorn

# Копируем код
WORKDIR /app
COPY ./src ./src

# Запуск API
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
'@

$dockerfilePath = "$TargetPath\Dockerfile"
[System.IO.File]::WriteAllText($dockerfilePath, $dockerfile, [System.Text.Encoding]::UTF8)
Write-Host "✅ Создан файл: $dockerfilePath" -ForegroundColor Green

# Файл 3: docker-compose.yml
$dockerCompose = @'
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
'@

$dockerComposePath = "$TargetPath\docker-compose.yml"
[System.IO.File]::WriteAllText($dockerComposePath, $dockerCompose, [System.Text.Encoding]::UTF8)
Write-Host "✅ Создан файл: $dockerComposePath" -ForegroundColor Green

# Файл 4: requirements.txt
$requirements = @'
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
'@

$requirementsPath = "$TargetPath\requirements.txt"
[System.IO.File]::WriteAllText($requirementsPath, $requirements, [System.Text.Encoding]::UTF8)
Write-Host "✅ Создан файл: $requirementsPath" -ForegroundColor Green

# Файл 5: README.md
$readme = @'
# Reflexio Local — Минимальная версия

🚀 Локальная версия Reflexio 24/7 для тестирования.

## 🚀 Быстрый запуск

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
pip install -r requirements.txt

# Запуск
python -m uvicorn src.api.main:app --reload
```

## 🌐 Проверка

Откройте в браузере:
- http://localhost:8000/ — корневой эндпоинт
- http://localhost:8000/health — health check
- http://localhost:8000/docs — Swagger UI (автоматически)

## 📊 Статус

```powershell
# Проверка контейнеров
docker ps

# Логи
docker compose logs -f api
```

---

**Версия:** 1.0 (Local)  
**Статус:** ✅ Минимальная рабочая версия
'@

$readmePath = "$TargetPath\README.md"
[System.IO.File]::WriteAllText($readmePath, $readme, [System.Text.Encoding]::UTF8)
Write-Host "✅ Создан файл: $readmePath" -ForegroundColor Green

# Файл 6: .gitignore
$gitignore = @'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/

# Logs
logs/
*.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
'@

$gitignorePath = "$TargetPath\.gitignore"
[System.IO.File]::WriteAllText($gitignorePath, $gitignore, [System.Text.Encoding]::UTF8)
Write-Host "✅ Создан файл: $gitignorePath" -ForegroundColor Green

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "🎉 Локальная версия Reflexio создана!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "📁 Расположение: $TargetPath" -ForegroundColor Blue
Write-Host ""
Write-Host "🚀 Следующие шаги:" -ForegroundColor Yellow
Write-Host "  1. Перейдите в директорию:" -ForegroundColor White
Write-Host "     cd $TargetPath" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Запустите Docker:" -ForegroundColor White
Write-Host "     docker compose up --build" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Проверьте в браузере:" -ForegroundColor White
Write-Host "     http://localhost:8000/health" -ForegroundColor Gray
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
