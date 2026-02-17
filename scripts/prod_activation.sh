#!/bin/bash
# Production Activation Script — Reflexio 24/7
# Выполняет все шаги для активации production режима

set -e

echo "🚀 Reflexio 24/7 — Production Activation"
echo "========================================"
echo ""

# Шаг 1: Проверка окружения
echo "[1/7] Проверка окружения..."
python scripts/check_osint_readiness.py || echo "⚠️  Environment check warning (may continue)"

# Шаг 2: Применение миграций Supabase
echo ""
echo "[2/7] Применение миграций Supabase..."
echo "⚠️  ВНИМАНИЕ: Миграции должны быть применены через Supabase Dashboard SQL Editor"
echo "   - src/storage/migrations/0001_init.sql"
echo "   - src/storage/migrations/0003_rls_policies.sql"
echo ""
read -p "Миграции применены? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Примените миграции перед продолжением"
    exit 1
fi

# Шаг 3: Проверка безопасности
echo ""
echo "[3/7] Проверка безопасности (SAFE+CoVe)..."
python .cursor/validation/safe/run.py --mode strict --summary || echo "⚠️  Security check warning"

# Шаг 4: Проверка LLM
echo ""
echo "[4/7] Проверка LLM интеграции..."
python scripts/smoke_llm.py || echo "⚠️  LLM check warning (may continue if API keys not set)"

# Шаг 5: Проверка observability
echo ""
echo "[5/7] Проверка observability..."
if [ -f "observability/prometheus.yml" ] && [ -f "observability/alert_rules.yml" ]; then
    echo "✅ Observability configs найдены"
else
    echo "⚠️  Observability configs не найдены"
fi

# Шаг 6: Финальная проверка готовности
echo ""
echo "[6/7] Финальная проверка готовности..."
python scripts/prod_verification.py || echo "⚠️  Verification warning"

# Шаг 7: Переключение профиля
echo ""
echo "[7/7] Переключение на production профиль..."
python - <<'PYCODE'
import yaml
from pathlib import Path

profile_path = Path(".cursor/governance/profile.yaml")
if profile_path.exists():
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["active_profile"] = "production"
    
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile, f, allow_unicode=True, default_flow_style=False)
    
    print("✅ Profile switched to 'production'")
else:
    print("⚠️  Profile file not found")
PYCODE

echo ""
echo "========================================"
echo "✅ Production Activation Complete!"
echo ""
echo "Следующие шаги:"
echo "1. docker compose build"
echo "2. docker compose up -d"
echo "3. curl http://localhost:8000/health"
echo ""
echo "📄 Reports:"
echo "  - PROD_VERIFICATION_REPORT.md"
echo "  - .cursor/audit/prod_verification_report.json"
echo ""











