"""
Создаёт снапшот чеклиста с датой.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import yaml
import shutil
from pathlib import Path
from datetime import datetime

def snapshot_checklist(
    checklist_path: Path,
    history_dir: Path = Path("docs/history"),
) -> Path:
    """
    Создаёт снапшот чеклиста.
    
    Args:
        checklist_path: Путь к чеклисту
        history_dir: Директория для истории
        
    Returns:
        Путь к созданному снапшоту
    """
    history_dir.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    snapshot_name = f"sprint_checklist_{date_str}.yaml"
    snapshot_path = history_dir / snapshot_name
    
    # Копируем чеклист
    shutil.copy2(checklist_path, snapshot_path)
    
    print(f"✅ Снапшот создан: {snapshot_path}")
    return snapshot_path

def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Create checklist snapshot")
    parser.add_argument(
        "--checklist",
        default=".cursor/tasks/surpass_smart_noter_checklist.yaml",
        help="Path to checklist YAML file",
    )
    parser.add_argument(
        "--history-dir",
        default="docs/history",
        help="History directory",
    )
    
    args = parser.parse_args()
    
    checklist_path = Path(args.checklist)
    if not checklist_path.exists():
        print(f"❌ Checklist not found: {checklist_path}")
        return
    
    snapshot_path = snapshot_checklist(
        checklist_path,
        history_dir=Path(args.history_dir),
    )
    
    print(f"📸 Snapshot saved: {snapshot_path}")

if __name__ == "__main__":
    main()





