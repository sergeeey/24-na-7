#!/usr/bin/env python3
"""
CLI утилита для проверки здоровья MCP-сервисов.

Использование:
    python scripts/check_mcp_health.py [--summary] [--timeout 5]
"""
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from .cursor.validation.mcp_validator import validate_mcp_services, REPORT_FILE
import json
import argparse


def format_summary_table(results: dict) -> str:
    """Форматирует результаты в виде таблицы."""
    lines = []
    lines.append("=" * 80)
    lines.append("MCP Services Health Report")
    lines.append("=" * 80)
    lines.append(f"Timestamp: {results.get('timestamp', 'N/A')}")
    lines.append(f"Total Services: {results.get('total_services', 0)}")
    lines.append(f"Enabled: {results.get('enabled_services', 0)}")
    lines.append(f"Healthy: {results.get('healthy_services', 0)}")
    lines.append("-" * 80)
    lines.append(f"{'Service':<25} {'Status':<12} {'Latency (ms)':<15} {'Details':<30}")
    lines.append("-" * 80)
    
    for name, data in results.items():
        if name in ("timestamp", "total_services", "enabled_services", "healthy_services"):
            continue
        
        if not isinstance(data, dict):
            continue
        
        status = data.get("status", "unknown")
        latency = data.get("latency_ms")
        
        # Иконки статуса
        status_icon = {
            "ok": "✅",
            "warn": "⚠️",
            "fail": "❌",
            "disabled": "⚪",
            "error": "🔴",
            "unknown": "❓",
        }.get(status, "❓")
        
        status_display = f"{status_icon} {status.upper()}"
        
        latency_str = f"{latency:.2f}" if latency is not None else "N/A"
        
        details = data.get("error") or data.get("reason") or ""
        if len(details) > 28:
            details = details[:25] + "..."
        
        lines.append(f"{name:<25} {status_display:<12} {latency_str:<15} {details:<30}")
    
    lines.append("=" * 80)
    
    return "\n".join(lines)


def main():
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(
        description="Check MCP services health",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary table",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=2,
        help="Timeout for each service check (seconds)",
    )
    parser.add_argument(
        "--from-file",
        action="store_true",
        help="Read results from existing mcp_health.json file",
    )
    
    args = parser.parse_args()
    
    # Загружаем результаты
    if args.from_file and REPORT_FILE.exists():
        try:
            with open(REPORT_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load health report: {e}", file=sys.stderr)
            return 1
    else:
        # Запускаем проверку
        from .cursor.validation.mcp_validator import validate_mcp_services, METRICS_DIR
        
        results = validate_mcp_services()
        
        if "error" in results:
            print(f"❌ {results['error']}", file=sys.stderr)
            return 1
        
        # Сохраняем результаты
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Выводим результаты
    if args.summary:
        print(format_summary_table(results))
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # Код возврата
    enabled = results.get("enabled_services", 0)
    healthy = results.get("healthy_services", 0)
    
    if enabled > 0 and healthy < enabled:
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())













