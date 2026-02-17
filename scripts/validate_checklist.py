"""
Валидатор чеклиста спринта.
Проверяет консистентность дат, количества задач и метрик.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import sys

def load_checklist(path: Path) -> Dict[str, Any]:
    """Загружает YAML чеклист."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def count_tasks(checklist: Dict[str, Any]) -> int:
    """Подсчитывает фактическое количество задач."""
    count = 0
    for epic_key, epic_data in checklist.get("epics", {}).items():
        tasks = epic_data.get("tasks", [])
        count += len(tasks)
    return count

def validate_dates(checklist: Dict[str, Any]) -> List[str]:
    """Проверяет консистентность дат."""
    issues = []
    
    sprint_end = checklist.get("sprint_end")
    completed_at = checklist.get("completed_at")
    
    # Проверяем, что sprint_end совпадает с последней фазой
    phases = checklist.get("phases", {})
    if phases:
        last_phase = max(phases.values(), key=lambda p: p.get("end_date", ""))
        last_phase_end = last_phase.get("end_date")
        
        if sprint_end != last_phase_end:
            issues.append(
                f"Несостыковка дат: sprint_end={sprint_end}, последняя фаза={last_phase_end}"
            )
        
        if completed_at != last_phase_end:
            issues.append(
                f"Несостыковка дат: completed_at={completed_at}, последняя фаза={last_phase_end}"
            )
    
    return issues

def validate_task_count(checklist: Dict[str, Any]) -> List[str]:
    """Проверяет консистентность количества задач."""
    issues = []
    
    actual_count = count_tasks(checklist)
    declared_count = checklist.get("progress_summary", {}).get("total_tasks", 0)
    
    if actual_count != declared_count:
        issues.append(
            f"Несостыковка количества задач: фактически={actual_count}, в progress_summary={declared_count}"
        )
    
    return issues

def validate_metrics(checklist: Dict[str, Any]) -> List[str]:
    """Проверяет, что метрики с status='completed' имеют current значения."""
    issues = []
    
    for epic_key, epic_data in checklist.get("epics", {}).items():
        metrics = epic_data.get("metrics", [])
        for metric in metrics:
            if metric.get("status") == "completed" and metric.get("current") is None:
                issues.append(
                    f"Метрика '{metric.get('name')}' в {epic_key} помечена как completed, но current=null"
                )
    
    return issues

def calculate_file_hash(file_path: Path) -> str:
    """Вычисляет SHA256 хеш файла."""
    import hashlib
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def validate_checklist(checklist_path: Path) -> Dict[str, Any]:
    """
    Валидирует чеклист и возвращает отчёт.
    
    Returns:
        {
            "valid": bool,
            "issues": List[str],
            "warnings": List[str],
            "stats": Dict[str, Any],
        }
    """
    checklist = load_checklist(checklist_path)
    
    issues = []
    warnings = []
    
    # Проверка дат
    date_issues = validate_dates(checklist)
    issues.extend(date_issues)
    
    # Проверка количества задач
    task_issues = validate_task_count(checklist)
    issues.extend(task_issues)
    
    # Проверка метрик
    metric_issues = validate_metrics(checklist)
    warnings.extend(metric_issues)  # Это предупреждения, не блокеры
    
    # Статистика
    actual_task_count = count_tasks(checklist)
    completed_tasks = sum(
        1
        for epic in checklist.get("epics", {}).values()
        for task in epic.get("tasks", [])
        if task.get("status") == "completed"
    )
    
    stats = {
        "total_tasks": actual_task_count,
        "completed_tasks": completed_tasks,
        "sprint_start": checklist.get("sprint_start"),
        "sprint_end": checklist.get("sprint_end"),
        "completed_at": checklist.get("completed_at"),
        "status": checklist.get("status"),
        "file_hash": calculate_file_hash(checklist_path),
    }
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "stats": stats,
    }

def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate sprint checklist")
    parser.add_argument(
        "--checklist",
        default=".cursor/tasks/surpass_smart_noter_checklist.yaml",
        help="Path to checklist YAML file",
    )
    parser.add_argument(
        "--output",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix issues where possible",
    )
    
    args = parser.parse_args()
    
    checklist_path = Path(args.checklist)
    if not checklist_path.exists():
        print(f"❌ Checklist not found: {checklist_path}")
        sys.exit(1)
    
    result = validate_checklist(checklist_path)
    
    # Выводим результаты
    if result["valid"]:
        print("✅ Checklist валиден!")
    else:
        print("❌ Найдены проблемы:")
        for issue in result["issues"]:
            print(f"  - {issue}")
    
    if result["warnings"]:
        print("\n⚠️  Предупреждения:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    
    print(f"\n📊 Статистика:")
    print(f"  - Всего задач: {result['stats']['total_tasks']}")
    print(f"  - Завершено: {result['stats']['completed_tasks']}")
    print(f"  - Sprint: {result['stats']['sprint_start']} → {result['stats']['sprint_end']}")
    
    # Сохраняем JSON отчёт
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n📄 JSON отчёт сохранён: {output_path}")
    
    # Auto-fix
    if args.fix and not result["valid"]:
        print("\n🔧 Попытка автоматического исправления...")
        checklist = load_checklist(checklist_path)
        
        # Исправляем даты
        phases = checklist.get("phases", {})
        if phases:
            last_phase = max(phases.values(), key=lambda p: p.get("end_date", ""))
            last_phase_end = last_phase.get("end_date")
            checklist["sprint_end"] = last_phase_end
            checklist["completed_at"] = last_phase_end
        
        # Исправляем количество задач
        actual_count = count_tasks(checklist)
        if "progress_summary" not in checklist:
            checklist["progress_summary"] = {}
        checklist["progress_summary"]["total_tasks"] = actual_count
        checklist["progress_summary"]["completed_tasks"] = actual_count
        
        # Сохраняем исправленный чеклист
        with open(checklist_path, "w", encoding="utf-8") as f:
            yaml.dump(checklist, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        print(f"✅ Чеклист исправлен и сохранён: {checklist_path}")
    
    sys.exit(0 if result["valid"] else 1)

if __name__ == "__main__":
    main()

