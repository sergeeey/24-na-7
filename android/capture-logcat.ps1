# Сбор логов при падении Reflexio.
# 1) Запусти этот скрипт. 2) Открой приложение на устройстве. 3) Дождись падения. 4) Нажми Enter — логи сохранятся.

$logDir = "d:\24 na 7\.cursor"
$logFile = Join-Path $logDir "debug.log"

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

Write-Host "Очистка logcat..."
adb logcat -c
Write-Host "Готово. Открой Reflexio на устройстве, дождись падения, затем нажми Enter здесь."
Read-Host
adb logcat -d > $logFile
Write-Host "Логи сохранены: $logFile"
Write-Host "Последние строки:"
Get-Content $logFile -Tail 80
