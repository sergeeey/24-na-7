#!/usr/bin/env python3
"""
Построение графика динамики надёжности за дни стабилизации.

Создаёт JSON timeline и опционально PNG график.
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def load_day_metrics(day: int) -> dict:
    """Загружает метрики дня."""
    morning = Path(f".cursor/stabilization/day{day}/morning_metrics.json")
    evening = Path(f".cursor/stabilization/day{day}/evening_metrics.json")
    
    result = {
        "day": day,
        "morning": None,
        "evening": None,
    }
    
    if morning.exists():
        try:
            result["morning"] = json.loads(morning.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    if evening.exists():
        try:
            result["evening"] = json.loads(evening.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    return result


def build_timeline(days: list) -> dict:
    """Строит timeline из метрик дней."""
    timeline = {
        "created_at": datetime.now().isoformat(),
        "days": [],
        "reliability_history": [],
        "mcp_health_history": [],
        "governance_changes": [],
    }
    
    for day_num in days:
        day_data = load_day_metrics(day_num)
        
        if day_data["morning"] or day_data["evening"]:
            timeline["days"].append(day_data)
            
            # Извлекаем reliability
            for period in ["morning", "evening"]:
                if day_data[period]:
                    gov = day_data[period].get("governance", {})
                    if gov.get("status") == "ok":
                        reliability = gov.get("reliability_index")
                        if reliability is not None:
                            timeline["reliability_history"].append({
                                "day": day_num,
                                "period": period,
                                "timestamp": day_data[period].get("timestamp"),
                                "reliability": reliability,
                            })
            
            # Извлекаем MCP health
            for period in ["morning", "evening"]:
                if day_data[period]:
                    mcp = day_data[period].get("mcp", {})
                    if mcp.get("status") == "ok":
                        timeline["mcp_health_history"].append({
                            "day": day_num,
                            "period": period,
                            "timestamp": day_data[period].get("timestamp"),
                            "healthy": mcp.get("healthy_services", 0),
                            "enabled": mcp.get("enabled_services", 0),
                        })
            
            # Извлекаем изменения профиля
            if day_data["evening"]:
                gov = day_data["evening"].get("governance", {})
                if gov.get("status") == "ok":
                    profile = gov.get("active_profile")
                    if profile:
                        timeline["governance_changes"].append({
                            "day": day_num,
                            "timestamp": day_data["evening"].get("timestamp"),
                            "profile": profile,
                        })
    
    return timeline


def generate_graph(timeline: dict, output_path: Path) -> None:
    """Генерирует PNG график (если matplotlib доступен)."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime
    except ImportError:
        print("⚠️ matplotlib not available, skipping graph generation")
        return
    
    if not timeline["reliability_history"]:
        print("⚠️ No reliability data to plot")
        return
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # График 1: Reliability
    times = []
    values = []
    labels = []
    
    for point in timeline["reliability_history"]:
        try:
            time_str = point["timestamp"]
            if time_str:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                times.append(dt)
                values.append(point["reliability"])
                labels.append(f"Day {point['day']} {point['period'][0]}")
        except Exception:
            continue
    
    if times:
        ax1.plot(times, values, marker="o", linestyle="-", linewidth=2)
        ax1.axhline(y=0.95, color="g", linestyle="--", label="Target (0.95)")
        ax1.axhline(y=0.75, color="r", linestyle="--", label="Minimum (0.75)")
        ax1.set_ylabel("AI Reliability Index")
        ax1.set_title("Reliability Over Time")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
    
    # График 2: MCP Health
    if timeline["mcp_health_history"]:
        times_mcp = []
        healthy_counts = []
        enabled_counts = []
        
        for point in timeline["mcp_health_history"]:
            try:
                time_str = point["timestamp"]
                if time_str:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    times_mcp.append(dt)
                    healthy_counts.append(point["healthy"])
                    enabled_counts.append(point["enabled"])
            except Exception:
                continue
        
        if times_mcp:
            ax2.plot(times_mcp, healthy_counts, marker="o", label="Healthy", color="g")
            ax2.plot(times_mcp, enabled_counts, marker="s", label="Enabled", color="b", linestyle="--")
            ax2.set_ylabel("MCP Services")
            ax2.set_xlabel("Time")
            ax2.set_title("MCP Services Health")
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"✅ Graph saved: {output_path}")


def main():
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description="Build reliability timeline")
    parser.add_argument("--days", required=True, help="Comma-separated list of days (e.g., 1,2,3)")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON file")
    parser.add_argument("--graph", type=Path, help="Output PNG graph file (optional)")
    
    args = parser.parse_args()
    
    # Парсим дни
    days = [int(d.strip()) for d in args.days.split(",")]
    
    # Строим timeline
    timeline = build_timeline(days)
    
    # Сохраняем JSON
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(timeline, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    print(f"✅ Timeline saved: {args.output}")
    print(f"   Days: {len(timeline['days'])}")
    print(f"   Reliability points: {len(timeline['reliability_history'])}")
    print(f"   MCP health points: {len(timeline['mcp_health_history'])}")
    
    # Генерируем график если запрошен
    if args.graph:
        generate_graph(timeline, args.graph)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())













