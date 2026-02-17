"""
Обновляет STATUS_REPORT.md с метриками из чеклиста.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List

def load_checklist_metrics(checklist_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Загружает метрики из чеклиста."""
    with open(checklist_path, "r", encoding="utf-8") as f:
        checklist = yaml.safe_load(f)
    
    metrics_by_epic = {}
    
    for epic_key, epic_data in checklist.get("epics", {}).items():
        epic_name = epic_data.get("name", epic_key)
        metrics = epic_data.get("metrics", [])
        metrics_by_epic[epic_name] = metrics
    
    return metrics_by_epic

def format_metrics_markdown(metrics_by_epic: Dict[str, List[Dict[str, Any]]]) -> str:
    """Форматирует метрики в Markdown."""
    lines = []
    lines.append("## 📊 Метрики спринта")
    lines.append("")
    
    for epic_name, metrics in metrics_by_epic.items():
        lines.append(f"### {epic_name}")
        lines.append("")
        lines.append("| Метрика | Цель | Текущее значение | Статус |")
        lines.append("|---------|------|------------------|--------|")
        
        for metric in metrics:
            name = metric.get("name", "")
            target = metric.get("target", "")
            current = metric.get("current")
            status = metric.get("status", "pending")
            
            current_str = str(current) if current is not None else "—"
            status_emoji = "✅" if status == "completed" else "⚠️" if status == "in_progress" else "⏳"
            
            lines.append(f"| {name} | {target} | {current_str} | {status_emoji} |")
        
        lines.append("")
    
    return "\n".join(lines)

def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Update STATUS_REPORT.md with metrics")
    parser.add_argument(
        "--checklist",
        default=".cursor/tasks/surpass_smart_noter_checklist.yaml",
        help="Path to checklist YAML file",
    )
    parser.add_argument(
        "--status-report",
        default="docs/STATUS_REPORT.md",
        help="Path to STATUS_REPORT.md",
    )
    
    args = parser.parse_args()
    
    checklist_path = Path(args.checklist)
    status_report_path = Path(args.status_report)
    
    if not checklist_path.exists():
        print(f"❌ Checklist not found: {checklist_path}")
        return
    
    if not status_report_path.exists():
        print(f"❌ STATUS_REPORT.md not found: {status_report_path}")
        return
    
    # Загружаем метрики
    metrics_by_epic = load_checklist_metrics(checklist_path)
    
    # Форматируем в Markdown
    metrics_markdown = format_metrics_markdown(metrics_by_epic)
    
    # Читаем STATUS_REPORT.md
    content = status_report_path.read_text(encoding="utf-8")
    
    # Ищем секцию метрик и заменяем
    import re
    
    # Ищем существующую секцию метрик
    pattern = r"## 📊 Метрики спринта.*?(?=## |$)"
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, metrics_markdown + "\n\n", content, flags=re.DOTALL)
    else:
        # Добавляем в конец
        content += "\n\n" + metrics_markdown
    
    # Сохраняем
    status_report_path.write_text(content, encoding="utf-8")
    
    print(f"✅ STATUS_REPORT.md обновлён с метриками из чеклиста")

if __name__ == "__main__":
    main()





