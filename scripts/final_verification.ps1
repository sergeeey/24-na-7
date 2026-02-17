# 🧭 Финальная проверка готовности Reflexio 24/7 (Windows PowerShell)
# DevOps-инженерский чеклист перед production deployment

$ErrorActionPreference = "Continue"

param(
    [switch]$Verbose = $false
)

$passed = 0
$failed = 0
$warnings = 0

function Check {
    param([string]$Name, [scriptblock]$Command, [string]$Description = "")
    
    Write-Host -NoNewline "  [ ] $Name"
    if ($Description) {
        Write-Host " ($Description)"
    } else {
        Write-Host ""
    }
    
    try {
        $result = & $Command 2>&1
        if ($LASTEXITCODE -eq 0 -or -not $LASTEXITCODE) {
            Write-Host "`r  [✅] $Name" -ForegroundColor Green
            $script:passed++
            return $true
        } else {
            Write-Host "`r  [❌] $Name" -ForegroundColor Red
            if ($Verbose) {
                Write-Host "      Command: $Command" -ForegroundColor Gray
            }
            $script:failed++
            return $false
        }
    } catch {
        Write-Host "`r  [❌] $Name" -ForegroundColor Red
        $script:failed++
        return $false
    }
}

function Warn {
    param([string]$Message)
    Write-Host "  [⚠️] $Message" -ForegroundColor Yellow
    $script:warnings++
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "🧭 Финальная проверка готовности Reflexio 24/7" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# 1. Проверка чистоты среды
Write-Host "[1/8] Проверка чистоты среды" -ForegroundColor Blue
Write-Host "───────────────────────────────────────────────────────────────────"

if (Get-Command docker -ErrorAction SilentlyContinue) {
    $containers = docker ps --filter "name=reflexio" --format "{{.Names}}" 2>&1
    if ($containers -match "reflexio") {
        Warn "Найдены запущенные контейнеры Reflexio (можно очистить: docker compose down -v)"
    } else {
        Check "Нет запущенных контейнеров Reflexio" { $true }
    }
} else {
    Warn "Docker не найден (пропускаем проверку контейнеров)"
}

# 2. Проверка .env
Write-Host ""
Write-Host "[2/8] Проверка .env файла" -ForegroundColor Blue
Write-Host "───────────────────────────────────────────────────────────────────"

if (Test-Path ".env") {
    Check ".env файл существует" { Test-Path ".env" }
    
    $envContent = Get-Content ".env" -Raw
    Check "DB_BACKEND задан" { $envContent -match "^DB_BACKEND=" -and $envContent -notmatch "^DB_BACKEND=$" }
    Check "SUPABASE_URL задан" { $envContent -match "^SUPABASE_URL=" -and $envContent -notmatch "^SUPABASE_URL=$" }
    Check "SUPABASE_ANON_KEY задан" { $envContent -match "^SUPABASE_ANON_KEY=" -and $envContent -notmatch "^SUPABASE_ANON_KEY=$" }
    Check "OPENAI_API_KEY задан" { $envContent -match "^OPENAI_API_KEY=" -and $envContent -notmatch "^OPENAI_API_KEY=$" }
    Check "SAFE_MODE задан" { $envContent -match "^SAFE_MODE=" }
} else {
    Write-Host "  [❌] .env файл не найден" -ForegroundColor Red
    $failed++
}

# 3. Проверка API ключей
Write-Host ""
Write-Host "[3/8] Проверка API ключей (два мира)" -ForegroundColor Blue
Write-Host "───────────────────────────────────────────────────────────────────"

if (Test-Path "scripts/check_api_keys.py") {
    $result = python scripts/check_api_keys.py 2>&1
    if ($LASTEXITCODE -eq 0) {
        Check "API ключи настроены (Python .env + MCP)" { $true }
    } else {
        Warn "API ключи требуют внимания (запусти: python scripts/check_api_keys.py)"
    }
} else {
    Warn "scripts/check_api_keys.py не найден"
}

# 4. Проверка зависимостей
Write-Host ""
Write-Host "[4/8] Проверка зависимостей" -ForegroundColor Blue
Write-Host "───────────────────────────────────────────────────────────────────"

Check "FFmpeg установлен" { Get-Command ffmpeg -ErrorAction SilentlyContinue }
Check "Python доступен" { Get-Command python -ErrorAction SilentlyContinue }

try {
    $pyVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1
    if ([version]$pyVersion -ge [version]"3.11") {
        Check "Python версия >= 3.11" { $true }
    } else {
        Warn "Python версия $pyVersion (рекомендуется 3.11+)"
    }
} catch {
    Warn "Не удалось определить версию Python"
}

# 5. Проверка Docker
Write-Host ""
Write-Host "[5/8] Проверка Docker" -ForegroundColor Blue
Write-Host "───────────────────────────────────────────────────────────────────"

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Check "Docker установлен" { Get-Command docker -ErrorAction SilentlyContinue }
    Check "Docker Compose доступен" { Get-Command docker-compose -ErrorAction SilentlyContinue; if (-not $?) { docker compose version 2>&1 | Out-Null } }
    Check "Dockerfile.api существует" { Test-Path "Dockerfile.api" }
    Check "docker-compose.yml существует" { Test-Path "docker-compose.yml" }
} else {
    Warn "Docker не найден (можно использовать без Docker)"
}

# 6. Проверка API
Write-Host ""
Write-Host "[6/8] Проверка API endpoints" -ForegroundColor Blue
Write-Host "───────────────────────────────────────────────────────────────────"

try {
    $health = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($health.StatusCode -eq 200) {
        Check "API /health отвечает" { $true }
        
        try {
            $metrics = Invoke-WebRequest -Uri "http://localhost:8000/metrics/prometheus" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($metrics.StatusCode -eq 200) {
                Check "API /metrics/prometheus доступен" { $true }
            } else {
                Warn "API /metrics/prometheus не доступен"
            }
        } catch {
            Warn "API /metrics/prometheus не доступен"
        }
    }
} catch {
    Warn "API не запущен (нормально, если это первый запуск)"
}

# 7. Проверка Supabase
Write-Host ""
Write-Host "[7/8] Проверка Supabase" -ForegroundColor Blue
Write-Host "───────────────────────────────────────────────────────────────────"

if (Test-Path "src/storage/supabase_client.py") {
    $result = python -c "from src.storage.db import get_db_backend; db = get_db_backend(); print('ok')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Check "Supabase подключение работает" { $true }
    } else {
        Warn "Supabase подключение требует проверки"
    }
} else {
    Warn "Supabase клиент не найден"
}

# 8. Проверка файлов
Write-Host ""
Write-Host "[8/8] Проверка файлов системы" -ForegroundColor Blue
Write-Host "───────────────────────────────────────────────────────────────────"

Check "init.yaml playbook существует" { Test-Path ".cursor/playbooks/init.yaml" }
Check "first_launch.ps1 существует" { Test-Path "scripts/first_launch.ps1" }
Check "verify_full_pipeline.py существует" { Test-Path "scripts/verify_full_pipeline.py" }
Check "mcp.json существует" { Test-Path ".cursor/mcp.json" }

# Итоги
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "📊 ИТОГИ" -ForegroundColor Blue
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ✅ Пройдено: $passed" -ForegroundColor Green
Write-Host "  ❌ Провалено: $failed" -ForegroundColor Red
Write-Host "  ⚠️  Предупреждений: $warnings" -ForegroundColor Yellow
Write-Host ""

if ($failed -eq 0) {
    Write-Host "🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Система готова к запуску:"
    Write-Host "  • .\scripts\first_launch.ps1"
    Write-Host ""
    exit 0
} else {
    Write-Host "❌ ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ" -ForegroundColor Red
    Write-Host ""
    Write-Host "Исправьте ошибки и запустите проверку снова."
    Write-Host ""
    exit 1
}











