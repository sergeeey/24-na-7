"""
Скрипт для обновления прогресса аудита.
Обновляет PROGRESS_TRACKER.md на основе выполненных задач.

Usage:
    python scripts/update_audit_progress.py --week 1 --task P0-2 --status done
    python scripts/update_audit_progress.py --week 1 --complete
"""

import argparse
import re
from datetime import datetime
from pathlib import Path


def update_progress(week: int, task: str = None, status: str = None, complete: bool = False):
    """Обновляет файл прогресса."""
    
    tracker_path = Path("PROGRESS_TRACKER.md")
    
    if not tracker_path.exists():
        print(f"❌ Файл {tracker_path} не найден!")
        return False
    
    content = tracker_path.read_text(encoding="utf-8")
    
    if complete:
        # Отметить всю неделю как выполненную
        pattern = rf"(### Неделя {week}.*?)(\[░░░░░░░░░░░░░░░░░░░░\] 0%)"
        replacement = rf"\1[████████████████████] 100%"
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        # Обновить все задачи недели
        pattern_tasks = rf"(### Неделя {week}.*?)(⬜)"
        replacement = r"\1✅"
        content = re.sub(pattern_tasks, replacement, content, flags=re.DOTALL)
        
        print(f"✅ Неделя {week} отмечена как выполненная!")
    
    elif task and status:
        # Обновить конкретную задачу
        if status == "done":
            # Найти задачу в таблице и заменить ⬜ на ✅
            pattern = rf"(\| {task} \|.*?\| )⬜( \|)"
            replacement = r"\1✅\2"
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                print(f"✅ Задача {task} отмечена как выполненная!")
            else:
                print(f"⚠️ Задача {task} не найдена или уже выполнена")
        elif status == "in_progress":
            pattern = rf"(\| {task} \|.*?\| )⬜( \|)"
            replacement = r"\1🔄\2"
            content = re.sub(pattern, replacement, content)
            print(f"🔄 Задача {task} отмечена как в работе!")
    
    # Добавить запись в историю
    today = datetime.now().strftime("%Y-%m-%d")
    history_entry = f"| {today} | | Обновлен прогресс: Неделя {week}"
    
    if task:
        history_entry += f", задача {task} = {status}"
    
    # Найти таблицу истории и добавить запись
    pattern = r"(\| Дата \| Версия \| Изменения \|\n\|------\|--------\|-----------\|)"
    replacement = rf"\1\n{history_entry} |"
    content = re.sub(pattern, replacement, content)
    
    # Сохранить
    tracker_path.write_text(content, encoding="utf-8")
    print(f"💾 Файл {tracker_path} обновлен!")
    
    return True


def show_stats():
    """Показывает текущую статистику."""
    tracker_path = Path("PROGRESS_TRACKER.md")
    
    if not tracker_path.exists():
        print("❌ Файл прогресса не найден!")
        return
    
    content = tracker_path.read_text(encoding="utf-8")
    
    # Подсчитать P0
    p0_done = content.count("P0-") - content.count("P0- | ⬜")
    p0_total = 6
    
    # Подсчитать P1
    p1_done = content.count("P1-") - content.count("P1- | ⬜")
    p1_total = 4
    
    print("\n" + "="*50)
    print("📊 ТЕКУЩАЯ СТАТИСТИКА")
    print("="*50)
    print(f"\n🔴 P0 (Critical): {p0_done}/{p0_total} ({p0_done/p0_total*100:.0f}%)")
    print(f"🟡 P1 (High):     {p1_done}/{p1_total} ({p1_done/p1_total*100:.0f}%)")
    print(f"\n📈 Общий прогресс: {(p0_done + p1_done)/(p0_total + p1_total)*100:.0f}%")
    print("="*50)


def main():
    parser = argparse.ArgumentParser(
        description="Обновление прогресса аудита Reflexio 24/7"
    )
    parser.add_argument(
        "--week",
        type=int,
        required=True,
        help="Номер недели (1-4)"
    )
    parser.add_argument(
        "--task",
        type=str,
        help="ID задачи (например, P0-2)"
    )
    parser.add_argument(
        "--status",
        type=str,
        choices=["done", "in_progress", "todo"],
        help="Статус задачи"
    )
    parser.add_argument(
        "--complete",
        action="store_true",
        help="Отметить всю неделю как выполненную"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Показать статистику"
    )
    
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
        return
    
    if args.complete:
        update_progress(args.week, complete=True)
    elif args.task and args.status:
        update_progress(args.week, args.task, args.status)
    else:
        print("❌ Укажите --task и --status, или --complete, или --stats")
        parser.print_help()


if __name__ == "__main__":
    main()
