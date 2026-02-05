#!/bin/bash
# 🧭 Финальная проверка готовности Reflexio 24/7
# DevOps-инженерский чеклист перед production deployment

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

VERBOSE="${VERBOSE:-false}"

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "🧭 Финальная проверка готовности Reflexio 24/7"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

PASSED=0
FAILED=0
WARNINGS=0

check() {
    local name="$1"
    local command="$2"
    local description="${3:-}"
    
    echo -n "  [ ] $name"
    if [ -n "$description" ]; then
        echo " ($description)"
    else
        echo ""
    fi
    
    if eval "$command" >/dev/null 2>&1; then
        echo -e "\r  ${GREEN}[✅]${NC} $name"
        ((PASSED++))
        return 0
    else
        echo -e "\r  ${RED}[❌]${NC} $name"
        if [ "$VERBOSE" = "true" ]; then
            echo "      Command: $command"
        fi
        ((FAILED++))
        return 1
    fi
}

warn() {
    local name="$1"
    echo -e "  ${YELLOW}[⚠️]${NC} $name"
    ((WARNINGS++))
}

# 1. Проверка чистоты среды
echo -e "${BLUE}[1/8]${NC} Проверка чистоты среды"
echo "───────────────────────────────────────────────────────────────────"

if command -v docker &> /dev/null; then
    if docker ps --filter "name=reflexio" --format "{{.Names}}" | grep -q reflexio; then
        warn "Найдены запущенные контейнеры Reflexio (можно очистить: docker compose down -v)"
    else
        check "Нет запущенных контейнеров Reflexio" "true"
    fi
else
    warn "Docker не найден (пропускаем проверку контейнеров)"
fi

# 2. Проверка .env
echo ""
echo -e "${BLUE}[2/8]${NC} Проверка .env файла"
echo "───────────────────────────────────────────────────────────────────"

if [ -f ".env" ]; then
    check ".env файл существует" "test -f .env"
    
    check "DB_BACKEND задан" "grep -q '^DB_BACKEND=' .env"
    check "SUPABASE_URL задан" "grep -q '^SUPABASE_URL=' .env && ! grep -q '^SUPABASE_URL=$' .env"
    check "SUPABASE_ANON_KEY задан" "grep -q '^SUPABASE_ANON_KEY=' .env && ! grep -q '^SUPABASE_ANON_KEY=$' .env"
    check "OPENAI_API_KEY задан" "grep -q '^OPENAI_API_KEY=' .env && ! grep -q '^OPENAI_API_KEY=$' .env"
    check "SAFE_MODE задан" "grep -q '^SAFE_MODE=' .env"
else
    echo -e "  ${RED}[❌]${NC} .env файл не найден"
    ((FAILED++))
fi

# 3. Проверка API ключей (оба мира)
echo ""
echo -e "${BLUE}[3/8]${NC} Проверка API ключей (два мира)"
echo "───────────────────────────────────────────────────────────────────"

if [ -f "scripts/check_api_keys.py" ]; then
    if python scripts/check_api_keys.py >/dev/null 2>&1; then
        check "API ключи настроены (Python .env + MCP)" "true"
    else
        warn "API ключи требуют внимания (запусти: python scripts/check_api_keys.py)"
    fi
else
    warn "scripts/check_api_keys.py не найден"
fi

# 4. Проверка FFmpeg
echo ""
echo -e "${BLUE}[4/8]${NC} Проверка зависимостей"
echo "───────────────────────────────────────────────────────────────────"

check "FFmpeg установлен" "command -v ffmpeg"
check "Python доступен" "command -v python"

PYTHON_VERSION=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
if [ "$(printf '%s\n' "3.11" "$PYTHON_VERSION" | sort -V | head -n1)" = "3.11" ]; then
    check "Python версия >= 3.11" "true"
else
    warn "Python версия $PYTHON_VERSION (рекомендуется 3.11+)"
fi

# 5. Проверка Docker (если есть)
echo ""
echo -e "${BLUE}[5/8]${NC} Проверка Docker"
echo "───────────────────────────────────────────────────────────────────"

if command -v docker &> /dev/null; then
    check "Docker установлен" "command -v docker"
    check "Docker Compose доступен" "command -v docker-compose || docker compose version"
    check "Dockerfile.api существует" "test -f Dockerfile.api"
    check "docker-compose.yml существует" "test -f docker-compose.yml"
else
    warn "Docker не найден (можно использовать без Docker)"
fi

# 6. Проверка API (если запущен)
echo ""
echo -e "${BLUE}[6/8]${NC} Проверка API endpoints"
echo "───────────────────────────────────────────────────────────────────"

if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    check "API /health отвечает" "true"
    
    if curl -fsS http://localhost:8000/metrics/prometheus >/dev/null 2>&1; then
        check "API /metrics/prometheus доступен" "true"
    else
        warn "API /metrics/prometheus не доступен"
    fi
else
    warn "API не запущен (нормально, если это первый запуск)"
fi

# 7. Проверка Supabase (если доступно)
echo ""
echo -e "${BLUE}[7/8]${NC} Проверка Supabase"
echo "───────────────────────────────────────────────────────────────────"

if [ -f "src/storage/supabase_client.py" ]; then
    if python -c "from src.storage.db import get_db_backend; db = get_db_backend(); print('ok')" >/dev/null 2>&1; then
        check "Supabase подключение работает" "true"
    else
        warn "Supabase подключение требует проверки"
    fi
else
    warn "Supabase клиент не найден"
fi

# 8. Проверка файлов инициализации
echo ""
echo -e "${BLUE}[8/8]${NC} Проверка файлов системы"
echo "───────────────────────────────────────────────────────────────────"

check "init.yaml playbook существует" "test -f .cursor/playbooks/init.yaml"
check "first_launch.sh существует" "test -f scripts/first_launch.sh"
check "verify_full_pipeline.py существует" "test -f scripts/verify_full_pipeline.py"
check "mcp.json существует" "test -f .cursor/mcp.json"

# Итоги
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo -e "${BLUE}📊 ИТОГИ${NC}"
echo "═══════════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}✅ Пройдено:${NC} $PASSED"
echo -e "  ${RED}❌ Провалено:${NC} $FAILED"
echo -e "  ${YELLOW}⚠️  Предупреждений:${NC} $WARNINGS"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!${NC}"
    echo ""
    echo "Система готова к запуску:"
    echo "  • ./scripts/first_launch.sh (Linux/macOS)"
    echo "  • .\\scripts\\first_launch.ps1 (Windows)"
    echo ""
    exit 0
else
    echo -e "${RED}❌ ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ${NC}"
    echo ""
    echo "Исправьте ошибки и запустите проверку снова."
    echo ""
    exit 1
fi











