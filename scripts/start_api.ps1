# Кроссплатформенный скрипт запуска API (Windows PowerShell)
# Для Linux/macOS используйте start_api.sh

param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

# Проверка порта
$socket = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Parse($Host), $Port)
try {
    $socket.Start()
    $socket.Stop()
    Write-Host "[start-api] ✅ Порт $Host`:$Port свободен"
} catch {
    Write-Host "[start-api] ❌ Порт $Host`:$Port занят"
    exit 1
}

# Создаём директории если нужно
if (-not (Test-Path ".cursor/logs")) {
    New-Item -ItemType Directory -Path ".cursor/logs" -Force | Out-Null
}

# Запускаем API в фоне
Write-Host "[start-api] 🚀 Запуск API на http://$Host`:$Port..."

$process = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "src.api.main:app", "--host", $Host, "--port", $Port, "--log-level", "info" `
    -RedirectStandardOutput ".cursor/logs/api.log" `
    -RedirectStandardError ".cursor/logs/api.log" `
    -PassThru `
    -NoNewWindow

$process.Id | Out-File -FilePath ".cursor/server.pid" -Encoding UTF8
Write-Host "[start-api] PID: $($process.Id)"

# Ожидание готовности
Write-Host "[start-api] ⏳ Ожидание готовности /health..."
$healthUrl = "http://$Host`:$Port/health"
$maxAttempts = 30

for ($i = 1; $i -le $maxAttempts; $i++) {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "[start-api] ✅ API готов: http://$Host`:$Port (PID: $($process.Id))"
            exit 0
        }
    } catch {
        # Продолжаем ожидание
    }
    Start-Sleep -Seconds 1
}

Write-Host "[start-api] ❌ API не ответил на /health в течение 30 секунд"
Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
Remove-Item -Path ".cursor/server.pid" -Force -ErrorAction SilentlyContinue
exit 1











