#!/bin/bash
# Обновляет Caddyfile на VPS и перезагружает Caddy.
# Запускать с ПК, где есть SSH-доступ к серверу.
#
# Использование:
#   REFLEXIO_SERVER=root@reflexio247.duckdns.org  ./scripts/update_caddy_on_server.sh
# или (если IP известен):
#   REFLEXIO_SERVER=root@1.2.3.4  ./scripts/update_caddy_on_server.sh
#
# Требуется: Caddyfile в корне проекта (уже с reflexio247.duckdns.org).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CADDYFILE_SRC="$REPO_ROOT/Caddyfile"
CADDYFILE_DEST="/etc/caddy/Caddyfile"

SERVER="${REFLEXIO_SERVER:?Set REFLEXIO_SERVER, e.g. REFLEXIO_SERVER=root@reflexio247.duckdns.org}"

if [ ! -f "$CADDYFILE_SRC" ]; then
    echo "Error: Caddyfile not found at $CADDYFILE_SRC"
    exit 1
fi

echo "Updating Caddy on $SERVER..."
echo "  Copying Caddyfile..."
scp "$CADDYFILE_SRC" "$SERVER:$CADDYFILE_DEST"
echo "  Reloading Caddy..."
ssh "$SERVER" "systemctl reload caddy"
echo "Done. Check: https://reflexio247.duckdns.org/health"
