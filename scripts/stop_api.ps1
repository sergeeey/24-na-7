# Кроссплатформенный скрипт остановки API (Windows PowerShell)
# Для Linux/macOS используйте stop_api.sh

$ErrorActionPreference = "Continue"

$PidFile = ".cursor/server.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "[stop-api] ⚠️  PID файл не найден (API может быть не запущен)"
    exit 0
}

$Pid = Get-Content $PidFile -Raw | ForEach-Object { [int]::Parse($_.Trim()) }

try {
    $process = Get-Process -Id $Pid -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "[stop-api] ⏹️  Остановка API (PID: $Pid)..."
        Stop-Process -Id $Pid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        
        # Проверяем что процесс остановлен
        $stillRunning = Get-Process -Id $Pid -ErrorAction SilentlyContinue
        if ($stillRunning) {
            Write-Host "[stop-api] ⚠️  Процесс не остановился, принудительное завершение..."
            Stop-Process -Id $Pid -Force -ErrorAction SilentlyContinue
        }
        
        Write-Host "[stop-api] ✅ API остановлен"
    } else {
        Write-Host "[stop-api] ⚠️  Процесс с PID $Pid не найден"
    }
} catch {
    Write-Host "[stop-api] ⚠️  Ошибка при остановке: $_"
}

Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue











