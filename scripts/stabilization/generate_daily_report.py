#!/usr/bin/env python3
"""
Генерация дневного отчёта стабилизации.

Создаёт markdown отчёт с результатами дня.
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def load_metrics(day: int) -> dict:
    """Загружает все метрики дня."""
    base = Path(f".cursor/stabilization/day{day}")
    
    metrics = {
        "morning": None,
        "evening": None,
        "health": None,
        "mcp_morning": None,
        "mcp_evening": None,
    }
    
    if (base / "morning_metrics.json").exists():
        try:
            metrics["morning"] = json.loads((base / "morning_metrics.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    
    if (base / "evening_metrics.json").exists():
        try:
            metrics["evening"] = json.loads((base / "evening_metrics.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    
    if (base / "health_check.json").exists():
        try:
            metrics["health"] = json.loads((base / "health_check.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    
    if (base / "mcp_health_morning.json").exists():
        try:
            metrics["mcp_morning"] = json.loads((base / "mcp_health_morning.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    
    if (base / "mcp_health_evening.json").exists():
        try:
            metrics["mcp_evening"] = json.loads((base / "mcp_health_evening.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    
    return metrics


def generate_report(day: int, metrics: dict) -> str:
    """Генерирует markdown отчёт."""
    lines = []
    
    lines.append(f"# Day {day} Stabilization Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().isoformat()}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Summary
    lines.append("## Summary")
    lines.append("")
    
    if metrics["health"]:
        overall = metrics["health"].get("overall_status", "unknown")
        status_icon = {
            "ok": "✅",
            "warning": "⚠️",
            "error": "❌",
        }.get(overall, "❓")
        
        lines.append(f"**Overall Status:** {status_icon} {overall.upper()}")
        lines.append("")
        
        for name, check in metrics["health"].get("checks", {}).items():
            status_icon = {
                "ok": "✅",
                "warning": "⚠️",
                "error": "❌",
            }.get(check.get("status"), "❓")
            
            lines.append(f"- {status_icon} **{name}:** {check.get('message', 'N/A')}")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Metrics Comparison
    lines.append("## Metrics Comparison (Morning → Evening)")
    lines.append("")
    
    if metrics["morning"] and metrics["evening"]:
        # Reliability
        morning_reliability = metrics["morning"].get("governance", {}).get("reliability_index")
        evening_reliability = metrics["evening"].get("governance", {}).get("reliability_index")
        
        if morning_reliability is not None and evening_reliability is not None:
            diff = evening_reliability - morning_reliability
            diff_str = f"+{diff:.3f}" if diff >= 0 else f"{diff:.3f}"
            lines.append(f"- **Reliability:** {morning_reliability:.3f} → {evening_reliability:.3f} ({diff_str})")
        
        # MCP Services
        morning_healthy = metrics["morning"].get("mcp", {}).get("healthy_services", 0)
        evening_healthy = metrics["evening"].get("mcp", {}).get("healthy_services", 0)
        morning_enabled = metrics["morning"].get("mcp", {}).get("enabled_services", 0)
        evening_enabled = metrics["evening"].get("mcp", {}).get("enabled_services", 0)
        
        lines.append(f"- **MCP Services:** {morning_healthy}/{morning_enabled} → {evening_healthy}/{evening_enabled}")
        
        # Database
        morning_db = metrics["morning"].get("database", {})
        evening_db = metrics["evening"].get("database", {})
        
        if morning_db.get("status") == "ok" and evening_db.get("status") == "ok":
            morning_pending = morning_db.get("pending_queue", 0)
            evening_pending = evening_db.get("pending_queue", 0)
            lines.append(f"- **Pending Queue:** {morning_pending} → {evening_pending}")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # MCP Services Details
    if metrics["mcp_evening"]:
        lines.append("## MCP Services Health")
        lines.append("")
        
        healthy = metrics["mcp_evening"].get("healthy_services", 0)
        enabled = metrics["mcp_evening"].get("enabled_services", 0)
        
        lines.append(f"**Status:** {healthy}/{enabled} services healthy")
        lines.append("")
        
        for name, info in metrics["mcp_evening"].items():
            if name in ("timestamp", "total_services", "enabled_services", "healthy_services"):
                continue
            
            if isinstance(info, dict):
                status = info.get("status", "unknown")
                latency = info.get("latency_ms")
                
                status_icon = {
                    "ok": "✅",
                    "warn": "⚠️",
                    "fail": "❌",
                    "disabled": "⚪",
                }.get(status, "❓")
                
                if latency is not None:
                    lines.append(f"- {status_icon} **{name}:** {status} ({latency:.2f}ms)")
                else:
                    lines.append(f"- {status_icon} **{name}:** {status}")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Next Steps
    lines.append("## Next Steps")
    lines.append("")
    
    if day < 3:
        lines.append(f"Continue with Day {day + 1}:")
        lines.append("")
        lines.append("```bash")
        lines.append(f"@playbook stabilization-reflexio --day {day + 1}")
        lines.append("```")
    else:
        lines.append("Stabilization period complete. Run final audit:")
        lines.append("")
        lines.append("```bash")
        lines.append("@playbook audit-standard")
        lines.append("```")
        lines.append("")
        lines.append("Check if score ≥ 85 for Level 5 — Self-Adaptive.")
    
    return "\n".join(lines)


def main():
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description="Generate daily stabilization report")
    parser.add_argument("--day", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    
    args = parser.parse_args()
    
    # Загружаем метрики
    metrics = load_metrics(args.day)
    
    # Генерируем отчёт
    report = generate_report(args.day, metrics)
    
    # Сохраняем
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    
    print(f"✅ Daily report generated: {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())













