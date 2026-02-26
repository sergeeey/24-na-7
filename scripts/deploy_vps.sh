#!/bin/bash
# deploy_vps.sh — Скрипт первичного деплоя Reflexio на VPS (Ubuntu 22.04)
#
# Использование:
#   ssh root@<VPS_IP>
#   curl -fsSL https://raw.githubusercontent.com/твой-репо/main/scripts/deploy_vps.sh | bash
# ИЛИ:
#   scp scripts/deploy_vps.sh root@<VPS_IP>:/root/
#   ssh root@<VPS_IP> bash deploy_vps.sh

set -e  # Остановить при любой ошибке

REPO_URL="${REPO_URL:-https://github.com/ВАШ_GITHUB/24-na-7.git}"
APP_DIR="/opt/reflexio"
DOMAIN="${DOMAIN:-reflexio.duckdns.org}"

echo "======================================"
echo "  Reflexio 24/7 — VPS Deploy Script"
echo "======================================"
echo "Domain: $DOMAIN"
echo "App dir: $APP_DIR"
echo ""

# ── 1. Системные зависимости ──────────────────────────
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq git curl

# ── 2. Docker ─────────────────────────────────────────
echo "[2/6] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "Docker installed."
else
    echo "Docker already installed."
fi

# ── 3. Caddy (reverse proxy + auto SSL) ───────────────
echo "[3/6] Installing Caddy..."
if ! command -v caddy &> /dev/null; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy
    mkdir -p /var/log/caddy
    echo "Caddy installed."
else
    echo "Caddy already installed."
fi

# ── 4. Клонирование репозитория ───────────────────────
echo "[4/6] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "Directory exists, pulling latest..."
    git -C "$APP_DIR" pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
mkdir -p src/storage

# ── 5. Конфигурация ────────────────────────────────────
echo "[5/6] Configuration..."

# .env — если не существует, создаём из шаблона
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.prod.example" "$APP_DIR/.env"
    echo ""
    echo "⚠️  ВАЖНО: Отредактируй .env перед запуском:"
    echo "    nano $APP_DIR/.env"
    echo "    Замени все <...> на реальные значения API ключей"
    echo ""
    read -p "Нажми Enter когда отредактируешь .env..." _
fi

# Caddy конфиг
cp "$APP_DIR/Caddyfile" /etc/caddy/Caddyfile
# Заменяем домен если задан
sed -i "s/reflexio.duckdns.org/$DOMAIN/g" /etc/caddy/Caddyfile
systemctl reload caddy
echo "Caddy configured for domain: $DOMAIN"

# ── 6. Запуск Docker Compose ──────────────────────────
echo "[6/6] Starting services..."
cd "$APP_DIR"
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "======================================"
echo "  ✅ Deploy complete!"
echo "======================================"
echo ""
echo "API: https://$DOMAIN"
echo "Health: https://$DOMAIN/health"
echo ""
echo "Полезные команды:"
echo "  docker compose -f $APP_DIR/docker-compose.prod.yml logs -f api"
echo "  docker compose -f $APP_DIR/docker-compose.prod.yml restart api"
echo "  journalctl -u caddy -f"
