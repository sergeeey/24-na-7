# Reflexio: удалить старую установку с устройства и поставить свежий APK.
# Требуется: подключённый телефон/эмулятор по USB, включённая отладка по USB.
# Запуск из корня:  .\android\install-fresh.ps1
# Запуск из android: .\install-fresh.ps1
#
# Чтобы приложение заработало:
# 1) Сервер должен быть доступен (у тебя в local.properties: wss://reflexio247.duckdns.org).
# 2) На телефоне: Настройки → Приложения → Reflexio → Разрешения: Микрофон, Уведомления.
# 3) При первом запуске разрешить запись аудио и не отключать оптимизацию батареи для Reflexio.

$ErrorActionPreference = "Stop"
$PackageId = "com.reflexio.app"
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$AndroidRoot = if (Test-Path (Join-Path $ScriptDir "app")) { $ScriptDir } else { Join-Path (Split-Path -Parent $ScriptDir) "android" }
$ApkPath = Join-Path $AndroidRoot "app\build\outputs\apk\debug\app-debug.apk"

if (-not (Test-Path $ApkPath)) {
    Write-Host "APK не найден. Собираю debug..." -ForegroundColor Yellow
    Push-Location $AndroidRoot
    & .\gradlew assembleDebug
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
    Pop-Location
}

$adb = Get-Command adb -ErrorAction SilentlyContinue
if (-not $adb) {
    $sdk = $env:ANDROID_HOME
    if (-not $sdk) { $sdk = $env:LOCALAPPDATA + "\Android\Sdk" }
    $adbExe = Join-Path $sdk "platform-tools\adb.exe"
    if (Test-Path $adbExe) { $adb = $adbExe } else {
        Write-Host "adb не найден. Добавьте Android SDK platform-tools в PATH или задайте ANDROID_HOME." -ForegroundColor Red
        exit 1
    }
} else { $adb = $adb.Source }

Write-Host "Удаляю старую установку $PackageId..." -ForegroundColor Cyan
& $adb uninstall $PackageId 2>$null
# Ошибка при uninstall если пакет не установлен — не критично

Write-Host "Устанавливаю $ApkPath ..." -ForegroundColor Cyan
& $adb install -r $ApkPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "Установка не удалась. Проверьте: $adb devices" -ForegroundColor Red
    exit 1
}

Write-Host "Готово. Запускаю приложение..." -ForegroundColor Green
& $adb shell am start -n "${PackageId}/.ui.MainActivity"
exit 0
