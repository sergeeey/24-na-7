#!/usr/bin/env python3
"""
Сбор ежедневных метрик состояния для стабилизации.

Собирает метрики утром и вечером каждого дня стабилизации.
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def collect_mcp_metrics() -> dict:
    """Собирает метрики MCP-сервисов."""
    mcp_health = Path(".cursor/metrics/mcp_health.json")
    
    if not mcp_health.exists():
        return {"status": "not_available"}
    
    try:
        data = json.loads(mcp_health.read_text(encoding="utf-8"))
        
        services = {}
        for name, info in data.items():
            if name in ("timestamp", "total_services", "enabled_services", "healthy_services"):
                continue
            
            if isinstance(info, dict):
                services[name] = {
                    "status": info.get("status", "unknown"),
                    "latency_ms": info.get("latency_ms"),
                }
        
        return {
            "status": "ok",
            "total_services": data.get("total_services", 0),
            "enabled_services": data.get("enabled_services", 0),
            "healthy_services": data.get("healthy_services", 0),
            "services": services,
            "timestamp": data.get("timestamp"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def collect_governance_metrics() -> dict:
    """Собирает метрики Governance."""
    profile = Path(".cursor/governance/profile.yaml")
    
    if not profile.exists():
        return {"status": "not_available"}
    
    try:
        import yaml
        data = yaml.safe_load(profile.read_text(encoding="utf-8"))
        
        return {
            "status": "ok",
            "active_profile": data.get("active_profile"),
            "current_level": data.get("current_level"),
            "reliability_index": data.get("reliability_index"),
            "context_hit_rate": data.get("context_hit_rate"),
            "last_audit_score": data.get("last_audit_score"),
            "mcp_governance": data.get("mcp_governance", {}),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def collect_api_metrics() -> dict:
    """Собирает метрики API (если доступен)."""
    import os
    
    try:
        import requests
        
        api_url = os.getenv("API_URL", "http://localhost:8000")
        response = requests.get(f"{api_url}/metrics", timeout=5)
        
        if response.status_code == 200:
            return {
                "status": "ok",
                "data": response.json(),
            }
        else:
            return {"status": "error", "status_code": response.status_code}
    except requests.exceptions.ConnectionError:
        return {"status": "not_running"}
    except ImportError:
        return {"status": "requests_not_available"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def collect_database_metrics() -> dict:
    """Собирает метрики базы данных."""
    db_path = Path("src/storage/reflexio.db")
    
    if not db_path.exists():
        return {"status": "not_exists"}
    
    try:
        import sqlite3
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Подсчитываем транскрипции
        cursor.execute("SELECT COUNT(*) FROM transcriptions")
        transcriptions_count = cursor.fetchone()[0]
        
        # Подсчитываем факты
        cursor.execute("SELECT COUNT(*) FROM facts")
        facts_count = cursor.fetchone()[0]
        
        # Подсчитываем в очереди
        cursor.execute("SELECT COUNT(*) FROM ingest_queue WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "status": "ok",
            "transcriptions_count": transcriptions_count,
            "facts_count": facts_count,
            "pending_queue": pending_count,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def collect_audit_metrics() -> dict:
    """Собирает метрики последнего аудита."""
    audit_report = Path(".cursor/audit/audit_report.json")
    
    if not audit_report.exists():
        return {"status": "not_available"}
    
    try:
        data = json.loads(audit_report.read_text(encoding="utf-8"))
        
        return {
            "status": "ok",
            "score": data.get("score"),
            "level": data.get("level"),
            "level_name": data.get("level_name"),
            "ai_reliability_index": data.get("ai_reliability_index"),
            "context_hit_rate": data.get("context_hit_rate"),
            "date": data.get("date"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def collect_daily_state(period: str) -> dict:
    """Собирает полное состояние системы."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "period": period,  # "morning" or "evening"
        "mcp": collect_mcp_metrics(),
        "governance": collect_governance_metrics(),
        "api": collect_api_metrics(),
        "database": collect_database_metrics(),
        "audit": collect_audit_metrics(),
    }


def main():
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description="Collect daily stabilization metrics")
    parser.add_argument("--day", type=int, required=True, help="Day number (1-3)")
    parser.add_argument("--period", choices=["morning", "evening"], required=True)
    parser.add_argument("--output", type=Path, required=True, help="Output JSON file")
    
    args = parser.parse_args()
    
    # Собираем состояние
    state = collect_daily_state(args.period)
    state["day"] = args.day
    
    # Сохраняем
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    print(f"✅ Daily state collected: {args.output}")
    print(f"   Period: {args.period}")
    print(f"   MCP services: {state['mcp'].get('healthy_services', 0)}/{state['mcp'].get('enabled_services', 0)}")
    print(f"   Governance profile: {state['governance'].get('active_profile', 'unknown')}")
    print(f"   Reliability: {state['governance'].get('reliability_index', 0):.2f}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())













