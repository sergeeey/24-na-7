#!/bin/bash
# Кроссплатформенный скрипт запуска API (Linux/macOS)
# Для Windows используйте start_api.ps1

set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8000}"

# Проверка порта
if python - <<PY
import socket, sys
s = socket.socket()
try:
    s.bind(("$HOST", int("$PORT")))
    s.close()
    sys.exit(0)
except OSError:
    sys.exit(1)
PY
then
    echo "[start-api] ✅ Порт $HOST:$PORT свободен"
else
    echo "[start-api] ❌ Порт $HOST:$PORT занят"
    exit 1
fi

# Создаём директории если нужно
mkdir -p .cursor/logs

# Запускаем API в фоне
echo "[start-api] 🚀 Запуск API на http://$HOST:$PORT..."
uvicorn src.api.main:app --host "$HOST" --port "$PORT" --log-level info > .cursor/logs/api.log 2>&1 &
PID=$!
echo $PID > .cursor/server.pid

echo "[start-api] ⏳ Ожидание готовности /health..."
for i in {1..30}; do
    if curl -fsS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
        echo "[start-api] ✅ API готов: http://$HOST:$PORT (PID: $PID)"
        exit 0
    fi
    sleep 1
done

echo "[start-api] ❌ API не ответил на /health в течение 30 секунд"
kill "$PID" 2>/dev/null || true
rm -f .cursor/server.pid
exit 1











