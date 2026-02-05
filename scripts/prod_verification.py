#!/usr/bin/env python3
"""
Production Verification Script — финальная проверка готовности Reflexio 24/7.
"""
import sys
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "pending",
    "profile": None,
    "level": None,
    "score": None,
    "checks": {},
    "metrics": {},
    "ready": False,
}


def check_env():
    """Проверка переменных окружения."""
    result = {"status": "ok", "issues": []}
    
    required = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
    ]
    
    optional = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "BRAVE_API_KEY",
        "BRIGHTDATA_API_KEY",
    ]
    
    for var in required:
        if not os.getenv(var):
            result["status"] = "fail"
            result["issues"].append(f"{var} not set")
    
    for var in optional:
        if not os.getenv(var):
            result["issues"].append(f"{var} not set (optional)")
    
    result["safe_mode"] = os.getenv("SAFE_MODE", "audit")
    result["db_backend"] = os.getenv("DB_BACKEND", "sqlite")
    
    return result


def check_supabase():
    """Проверка подключения к Supabase."""
    result = {"status": "unknown", "connection": False}
    
    try:
        from src.storage.supabase_client import test_connection
        test_result = test_connection()
        result["status"] = test_result.get("status", "unknown")
        result["connection"] = test_result.get("status") == "ok"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


def check_security():
    """Проверка SAFE+CoVe."""
    result = {"status": "unknown", "safe": False, "cove": False}
    
    # Проверка SAFE
    safe_path = Path(".cursor/validation/safe/checks.py")
    if safe_path.exists():
        result["safe"] = True
    
    # Проверка CoVe
    cove_path = Path(".cursor/validation/cove/verify.py")
    if cove_path.exists():
        result["cove"] = True
    
    result["status"] = "ok" if result["safe"] and result["cove"] else "warn"
    
    return result


def check_llm():
    """Проверка LLM интеграции."""
    result = {"status": "unknown", "provider": None, "available": False}
    
    provider = os.getenv("LLM_PROVIDER", "openai")
    result["provider"] = provider
    
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        result["available"] = True
        result["status"] = "ok"
    elif provider == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        result["available"] = True
        result["status"] = "ok"
    else:
        result["status"] = "warn"
        result["error"] = f"{provider} API key not set"
    
    return result


def check_observability():
    """Проверка observability компонентов."""
    result = {"status": "unknown", "components": {}}
    
    prometheus = Path("observability/prometheus.yml").exists()
    alerts = Path("observability/alert_rules.yml").exists()
    grafana = Path("observability/grafana_dashboards/reflexio.json").exists()
    
    result["components"] = {
        "prometheus": prometheus,
        "alerts": alerts,
        "grafana": grafana,
    }
    
    result["status"] = "ok" if prometheus and alerts and grafana else "warn"
    
    return result


def check_governance():
    """Проверка Governance профиля."""
    result = {"status": "unknown", "profile": None, "level": None, "score": None}
    
    profile_path = Path(".cursor/governance/profile.yaml")
    if profile_path.exists():
        try:
            import yaml
            profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            result["profile"] = profile.get("active_profile", "unknown")
            result["level"] = profile.get("current_level", 0)
            result["score"] = profile.get("last_audit_score", 0)
            result["status"] = "ok"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
    
    return result


def check_audit():
    """Проверка последнего аудита."""
    result = {"status": "unknown", "score": None, "level": None}
    
    audit_path = Path(".cursor/audit/audit_report.json")
    if audit_path.exists():
        try:
            data = json.loads(audit_path.read_text(encoding="utf-8"))
            result["score"] = data.get("score", 0)
            result["level"] = data.get("level", 0)
            result["status"] = "ok"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
    
    return result


def check_metrics():
    """Проверка метрик."""
    result = {"status": "unknown", "metrics": {}}
    
    metrics_path = Path("cursor-metrics.json")
    if metrics_path.exists():
        try:
            data = json.loads(metrics_path.read_text(encoding="utf-8"))
            result["metrics"] = data.get("metrics", {})
            result["status"] = "ok"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
    
    return result


def main():
    """Основная функция проверки."""
    global report
    
    print("\n" + "=" * 70)
    print("🚀 Reflexio 24/7 — Production Verification")
    print("=" * 70)
    print()
    
    # Проверки
    checks = {
        "environment": check_env,
        "supabase": check_supabase,
        "security": check_security,
        "llm": check_llm,
        "observability": check_observability,
        "governance": check_governance,
        "audit": check_audit,
        "metrics": check_metrics,
    }
    
    for name, check_func in checks.items():
        print(f"[{name.upper()}]")
        try:
            result = check_func()
            report["checks"][name] = result
            
            if result.get("status") == "ok":
                print(f"✅ {name}: OK")
            elif result.get("status") == "warn":
                print(f"⚠️  {name}: WARNING")
                if "issues" in result:
                    for issue in result["issues"]:
                        print(f"   - {issue}")
            else:
                print(f"❌ {name}: FAILED")
                if "error" in result:
                    print(f"   Error: {result['error']}")
        except Exception as e:
            print(f"❌ {name}: ERROR - {e}")
            report["checks"][name] = {"status": "error", "error": str(e)}
        print()
    
    # Собираем итоговые метрики
    governance_check = report["checks"].get("governance", {})
    audit_check = report["checks"].get("audit", {})
    metrics_check = report["checks"].get("metrics", {})
    
    report["profile"] = governance_check.get("profile")
    report["level"] = audit_check.get("level") or governance_check.get("level", 0)
    report["score"] = audit_check.get("score") or governance_check.get("score", 0)
    
    # Метрики из cursor-metrics.json
    metrics_data = metrics_check.get("metrics", {})
    report["metrics"] = {
        "ai_reliability_index": metrics_data.get("governance", {}).get("reliability_index"),
        "context_hit_rate": metrics_data.get("governance", {}).get("context_hit_rate"),
        "deepconf_confidence": metrics_data.get("osint", {}).get("avg_deepconf_confidence"),
    }
    
    # Определяем готовность
    critical_checks = ["environment", "security", "governance", "audit"]
    critical_ok = all(
        report["checks"].get(name, {}).get("status") in ("ok", "warn")
        for name in critical_checks
    )
    
    score_ok = report["score"] and report["score"] >= 90
    level_ok = report["level"] and report["level"] >= 5
    
    report["ready"] = critical_ok and score_ok and level_ok
    
    # Сохраняем отчёт
    report_path = Path(".cursor/audit/prod_verification_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # Итоги
    print("=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print(f"Profile: {report['profile']}")
    print(f"Level: {report['level']}")
    print(f"Score: {report['score']}")
    print(f"AI Reliability Index: {report['metrics'].get('ai_reliability_index')}")
    print(f"Context Hit Rate: {report['metrics'].get('context_hit_rate')}")
    print()
    
    if report["ready"]:
        report["status"] = "ready"
        print("✅ REFLEXIO 24/7 READY FOR PRODUCTION!")
        print("\n🚀 Production activation complete!")
        return 0
    else:
        report["status"] = "not_ready"
        print("⚠️  NOT READY FOR PRODUCTION")
        print("\nПроверьте указанные проблемы выше.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

