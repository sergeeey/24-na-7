# Обновляет Caddyfile на VPS и перезагружает Caddy.
# Запускать с ПК (PowerShell), где настроен SSH-доступ к серверу.
#
# Использование:
#   $env:REFLEXIO_SERVER = "root@reflexio247.duckdns.org"
#   .\scripts\update_caddy_on_server.ps1
# или одной строкой:
#   $env:REFLEXIO_SERVER = "root@reflexio247.duckdns.org"; .\scripts\update_caddy_on_server.ps1

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$caddyfileSrc = Join-Path $repoRoot "Caddyfile"
$caddyfileDest = "/etc/caddy/Caddyfile"

$server = $env:REFLEXIO_SERVER
if (-not $server) {
    Write-Host "Set REFLEXIO_SERVER, e.g.: `$env:REFLEXIO_SERVER = `"root@reflexio247.duckdns.org`"" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $caddyfileSrc)) {
    Write-Host "Error: Caddyfile not found at $caddyfileSrc" -ForegroundColor Red
    exit 1
}

Write-Host "Updating Caddy on $server..."
Write-Host "  Copying Caddyfile..."
scp $caddyfileSrc "${server}:${caddyfileDest}"
Write-Host "  Reloading Caddy..."
ssh $server "systemctl reload caddy"
Write-Host "Done. Check: https://reflexio247.duckdns.org/health" -ForegroundColor Green
