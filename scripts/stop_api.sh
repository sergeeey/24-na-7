#!/bin/bash
# Кроссплатформенный скрипт остановки API (Linux/macOS)
# Для Windows используйте stop_api.ps1

set -euo pipefail

PID_FILE=".cursor/server.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "[stop-api] ⚠️  PID файл не найден (API может быть не запущен)"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" >/dev/null 2>&1; then
    echo "[stop-api] ⏹️  Остановка API (PID: $PID)..."
    kill "$PID" || true
    sleep 1
    
    # Проверяем что процесс остановлен
    if ps -p "$PID" >/dev/null 2>&1; then
        echo "[stop-api] ⚠️  Процесс не остановился, принудительное завершение..."
        kill -9 "$PID" || true
    fi
    
    echo "[stop-api] ✅ API остановлен"
else
    echo "[stop-api] ⚠️  Процесс с PID $PID не найден"
fi

rm -f "$PID_FILE"











