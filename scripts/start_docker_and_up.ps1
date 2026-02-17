# Запуск Docker Desktop и поднятие контейнеров Reflexio 24/7
# Использование: powershell -ExecutionPolicy Bypass -File .\scripts\start_docker_and_up.ps1

$ErrorActionPreference = "Continue"

Write-Host "🚀 Reflexio 24/7 — Docker Startup" -ForegroundColor Cyan
Write-Host ""

# Проверка Docker Desktop
$dockerProc = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $dockerProc) {
    Write-Host "⏳ Запускаю Docker Desktop..." -ForegroundColor Yellow
    $dockerPath = "$Env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerPath) {
        Start-Process $dockerPath
        Write-Host "   Ожидание запуска Docker Engine..." -ForegroundColor Gray
    } else {
        Write-Host "❌ Docker Desktop не найден по пути: $dockerPath" -ForegroundColor Red
        Write-Host "   Установите Docker Desktop: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "✅ Docker Desktop уже запущен (PID: $($dockerProc.Id))" -ForegroundColor Green
}

# Ждём готовности движка (до 60 секунд)
Write-Host "⏳ Ожидание готовности Docker Engine..." -ForegroundColor Yellow
$ok = $false
1..60 | ForEach-Object {
    try {
        docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ok = $true
            Write-Host "✅ Docker Engine готов!" -ForegroundColor Green
            break
        }
    } catch {
        # Продолжаем ожидание
    }
    if ($_ % 10 -eq 0) {
        Write-Host "   ... ещё ожидаю (секунда $_)" -ForegroundColor Gray
    }
    Start-Sleep -Seconds 1
}

if (-not $ok) {
    Write-Host "❌ Docker Engine не поднялся за 60 секунд" -ForegroundColor Red
    Write-Host "   Проверьте Docker Desktop вручную и попробуйте снова" -ForegroundColor Yellow
    exit 1
}

# Переходим в папку проекта
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location $projectPath
Write-Host ""
Write-Host "📁 Рабочая директория: $projectPath" -ForegroundColor Cyan

# Проверка docker-compose.yml
if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "❌ docker-compose.yml не найден" -ForegroundColor Red
    exit 1
}

# Проверка .env
if (-not (Test-Path ".env")) {
    Write-Host "⚠️ .env файл не найден, создаю минимальный..." -ForegroundColor Yellow
    @"
DB_BACKEND=supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
OPENAI_API_KEY=
SAFE_MODE=strict
LOG_LEVEL=INFO
"@ | Out-File -FilePath ".env" -Encoding UTF8
    Write-Host "   ✅ Создан минимальный .env (заполните ключи!)" -ForegroundColor Yellow
}

# Остановка существующих контейнеров (если есть)
Write-Host ""
Write-Host "🛑 Остановка существующих контейнеров..." -ForegroundColor Yellow
docker compose down 2>&1 | Out-Null

# Поднимаем сервисы
Write-Host ""
Write-Host "🐳 Запуск контейнеров..." -ForegroundColor Cyan
docker compose up -d --build

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Контейнеры запущены!" -ForegroundColor Green
    Write-Host ""
    
    # Показываем статус
    Write-Host "📊 Статус контейнеров:" -ForegroundColor Cyan
    docker compose ps
    
    Write-Host ""
    Write-Host "🌐 API доступен на:" -ForegroundColor Cyan
    
    # Определяем порт из docker-compose.yml
    $composeContent = Get-Content "docker-compose.yml" -Raw
    if ($composeContent -match 'ports:\s+- "(\d+):8000"') {
        $externalPort = $matches[1]
        Write-Host "   http://127.0.0.1:$externalPort" -ForegroundColor Green
        Write-Host "   http://127.0.0.1:$externalPort/health" -ForegroundColor Gray
        Write-Host "   http://127.0.0.1:$externalPort/docs" -ForegroundColor Gray
    } else {
        Write-Host "   http://127.0.0.1:8000" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "📋 Полезные команды:" -ForegroundColor Cyan
    Write-Host "   docker compose logs -f          # Логи" -ForegroundColor Gray
    Write-Host "   docker compose ps                # Статус" -ForegroundColor Gray
    Write-Host "   docker compose restart           # Перезапуск" -ForegroundColor Gray
    Write-Host "   docker compose down              # Остановка" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "❌ Ошибка при запуске контейнеров" -ForegroundColor Red
    Write-Host "   Проверьте логи: docker compose logs" -ForegroundColor Yellow
    exit 1
}









