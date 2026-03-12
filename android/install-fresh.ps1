$ErrorActionPreference = "Stop"

$PackageId = "com.reflexio.app"
$ScriptDir = if ($PSScriptRoot) {
    $PSScriptRoot
} else {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}
$AndroidRoot = if (Test-Path (Join-Path $ScriptDir "app")) {
    $ScriptDir
} else {
    Join-Path (Split-Path -Parent $ScriptDir) "android"
}
$ApkPath = Join-Path $AndroidRoot "app\build\outputs\apk\debug\app-debug.apk"

if (-not (Test-Path $ApkPath)) {
    Write-Host "APK not found. Building debug..." -ForegroundColor Yellow
    Push-Location $AndroidRoot
    & .\gradlew.bat assembleDebug
    $buildExit = $LASTEXITCODE
    Pop-Location
    if ($buildExit -ne 0) {
        exit $buildExit
    }
}

$adbCommand = Get-Command adb -ErrorAction SilentlyContinue
if ($adbCommand) {
    $adb = $adbCommand.Source
} else {
    $sdkRoot = $env:ANDROID_HOME
    if (-not $sdkRoot) {
        $sdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    }
    $adb = Join-Path $sdkRoot "platform-tools\adb.exe"
    if (-not (Test-Path $adb)) {
        Write-Host "adb not found. Add platform-tools to PATH or configure ANDROID_HOME." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Uninstalling old package $PackageId..." -ForegroundColor Cyan
& $adb uninstall $PackageId | Out-Null

Write-Host "Installing $ApkPath..." -ForegroundColor Cyan
& $adb install -r $ApkPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "Install failed. Check adb devices." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Launching app..." -ForegroundColor Green
& $adb shell am start -n "$PackageId/.ui.MainActivity"
exit 0
