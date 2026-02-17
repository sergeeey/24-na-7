"""
Обновляет метрики в чеклисте фактическими значениями.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

def update_metric_current(
    checklist: Dict[str, Any],
    epic_key: str,
    metric_name: str,
    current_value: Any,
) -> bool:
    """
    Обновляет current значение метрики.
    
    Args:
        checklist: Словарь чеклиста
        epic_key: Ключ эпика (например, "epic_i_asr")
        metric_name: Имя метрики
        current_value: Фактическое значение
        
    Returns:
        True если обновлено
    """
    epic = checklist.get("epics", {}).get(epic_key)
    if not epic:
        return False
    
    metrics = epic.get("metrics", [])
    for metric in metrics:
        if metric.get("name") == metric_name:
            metric["current"] = current_value
            return True
    
    return False

def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Update metrics in checklist")
    parser.add_argument(
        "--checklist",
        default=".cursor/tasks/surpass_smart_noter_checklist.yaml",
        help="Path to checklist YAML file",
    )
    parser.add_argument(
        "--epic",
        required=True,
        help="Epic key (e.g., epic_i_asr)",
    )
    parser.add_argument(
        "--metric",
        required=True,
        help="Metric name",
    )
    parser.add_argument(
        "--value",
        required=True,
        help="Current value",
    )
    
    args = parser.parse_args()
    
    checklist_path = Path(args.checklist)
    if not checklist_path.exists():
        print(f"❌ Checklist not found: {checklist_path}")
        return
    
    # Загружаем чеклист
    with open(checklist_path, "r", encoding="utf-8") as f:
        checklist = yaml.safe_load(f)
    
    # Обновляем метрику
    success = update_metric_current(
        checklist,
        args.epic,
        args.metric,
        args.value,
    )
    
    if success:
        # Сохраняем
        with open(checklist_path, "w", encoding="utf-8") as f:
            yaml.dump(checklist, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"✅ Метрика '{args.metric}' в {args.epic} обновлена: {args.value}")
    else:
        print(f"❌ Метрика '{args.metric}' не найдена в {args.epic}")

if __name__ == "__main__":
    main()





