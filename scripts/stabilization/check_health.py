#!/usr/bin/env python3
"""
Проверка здоровья системы для стабилизации.

Проверяет все критические компоненты и выдаёт статус.
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def check_thresholds() -> dict:
    """Определяет пороги тревоги."""
    return {
        "mcp_latency_ms": 2000,
        "api_error_rate": 0.01,  # 1%
        "pending_queue": 10,
        "reliability_min": 0.75,
    }


def check_mcp_health(thresholds: dict) -> dict:
    """Проверяет здоровье MCP-сервисов."""
    mcp_health = Path(".cursor/metrics/mcp_health.json")
    
    if not mcp_health.exists():
        return {
            "status": "warning",
            "message": "MCP health report not found",
        }
    
    try:
        data = json.loads(mcp_health.read_text(encoding="utf-8"))
        
        issues = []
        healthy = data.get("healthy_services", 0)
        enabled = data.get("enabled_services", 0)
        
        # Проверяем латентность
        for name, info in data.items():
            if name in ("timestamp", "total_services", "enabled_services", "healthy_services"):
                continue
            
            if isinstance(info, dict):
                latency = info.get("latency_ms")
                if latency and latency > thresholds["mcp_latency_ms"]:
                    issues.append(f"{name}: high latency ({latency:.2f}ms)")
                
                if info.get("status") == "fail":
                    issues.append(f"{name}: service failed")
        
        if healthy < enabled:
            return {
                "status": "error",
                "message": f"Only {healthy}/{enabled} services healthy",
                "issues": issues,
            }
        elif issues:
            return {
                "status": "warning",
                "message": "Some services have issues",
                "issues": issues,
            }
        else:
            return {
                "status": "ok",
                "message": f"All {enabled} services healthy",
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to check MCP health: {str(e)}",
        }


def check_governance_stability(thresholds: dict) -> dict:
    """Проверяет стабильность Governance."""
    profile = Path(".cursor/governance/profile.yaml")
    
    if not profile.exists():
        return {
            "status": "error",
            "message": "Governance profile not found",
        }
    
    try:
        import yaml
        data = yaml.safe_load(profile.read_text(encoding="utf-8"))
        
        reliability = data.get("reliability_index", 0.0)
        
        if reliability < thresholds["reliability_min"]:
            return {
                "status": "warning",
                "message": f"Reliability below threshold ({reliability:.2f} < {thresholds['reliability_min']})",
            }
        
        # Проверяем частые переключения профиля (если есть история)
        alerts = data.get("mcp_governance", {}).get("alerts", [])
        if len(alerts) > 5:
            return {
                "status": "warning",
                "message": f"Too many governance alerts: {len(alerts)}",
            }
        
        return {
            "status": "ok",
            "message": f"Governance stable (reliability: {reliability:.2f})",
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to check governance: {str(e)}",
        }


def check_database_queue(thresholds: dict) -> dict:
    """Проверяет очередь транскрипций."""
    db_path = Path("src/storage/reflexio.db")
    
    if not db_path.exists():
        return {
            "status": "warning",
            "message": "Database not found",
        }
    
    try:
        import sqlite3
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ingest_queue WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0]
        conn.close()
        
        if pending_count > thresholds["pending_queue"]:
            return {
                "status": "warning",
                "message": f"Queue size above threshold ({pending_count} > {thresholds['pending_queue']})",
            }
        
        return {
            "status": "ok",
            "message": f"Queue healthy ({pending_count} pending)",
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to check queue: {str(e)}",
        }


def check_overall_health(thresholds: dict) -> dict:
    """Проверяет общее здоровье системы."""
    checks = {
        "mcp": check_mcp_health(thresholds),
        "governance": check_governance_stability(thresholds),
        "database_queue": check_database_queue(thresholds),
    }
    
    # Определяем общий статус
    statuses = [check["status"] for check in checks.values()]
    
    if "error" in statuses:
        overall_status = "error"
    elif "warning" in statuses:
        overall_status = "warning"
    else:
        overall_status = "ok"
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "checks": checks,
    }


def main():
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description="Check system health for stabilization")
    parser.add_argument("--day", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    
    args = parser.parse_args()
    
    thresholds = check_thresholds()
    health = check_overall_health(thresholds)
    health["day"] = args.day
    
    # Сохраняем
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(health, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    # Выводим краткую сводку
    print("=" * 70)
    print("System Health Check")
    print("=" * 70)
    print(f"Overall Status: {health['overall_status'].upper()}")
    print()
    
    for name, check in health["checks"].items():
        status_icon = {
            "ok": "✅",
            "warning": "⚠️",
            "error": "❌",
        }.get(check["status"], "❓")
        
        print(f"{status_icon} {name:20s} {check['message']}")
    
    print("=" * 70)
    
    return 0 if health["overall_status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())













