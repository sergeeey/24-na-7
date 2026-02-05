"""
Создаёт снимок метрик проекта.

Собирает информацию о размере кодовой базы, количестве тестов, покрытии и т.д.
"""
import json
from pathlib import Path
from datetime import datetime
import subprocess

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("metrics_snapshot")


def count_lines(path: Path, extensions: list[str]) -> int:
    """Подсчитывает строки кода в файлах с указанными расширениями."""
    total = 0
    for ext in extensions:
        for file_path in path.rglob(f"*.{ext}"):
            if file_path.is_file():
                try:
                    total += len(file_path.read_text(encoding="utf-8").splitlines())
                except Exception:
                    pass
    return total


def get_git_info() -> dict:
    """Получает информацию о Git репозитории."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit_hash = result.stdout.strip() if result.returncode == 0 else None
        
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = result.stdout.strip() if result.returncode == 0 else None
        
        return {
            "commit": commit_hash,
            "branch": branch,
        }
    except Exception:
        return {"commit": None, "branch": None}


def create_snapshot(include_api_metrics: bool = True) -> dict:
    """
    Создаёт снимок метрик проекта.
    
    Returns:
        Словарь с метриками
    """
    project_root = Path(".")
    src_path = project_root / "src"
    tests_path = project_root / "tests"
    
    # Подсчитываем строки кода
    src_lines = count_lines(src_path, ["py"]) if src_path.exists() else 0
    test_lines = count_lines(tests_path, ["py"]) if tests_path.exists() else 0
    
    # Подсчитываем файлы
    src_files = len(list(src_path.rglob("*.py"))) if src_path.exists() else 0
    test_files = len(list(tests_path.rglob("*.py"))) if tests_path.exists() else 0
    
    # Информация о Git
    git_info = get_git_info()
    
    # Размеры директорий
    storage_uploads = project_root / "src" / "storage" / "uploads"
    storage_recordings = project_root / "src" / "storage" / "recordings"
    
    uploads_count = len(list(storage_uploads.glob("*.wav"))) if storage_uploads.exists() else 0
    recordings_count = len(list(storage_recordings.glob("*.wav"))) if storage_recordings.exists() else 0
    
    snapshot = {
        "timestamp": datetime.utcnow().isoformat(),
        "project": "Reflexio 24/7",
        "version": "0.1.0",
        "metrics": {
            "code": {
                "src_lines": src_lines,
                "test_lines": test_lines,
                "src_files": src_files,
                "test_files": test_files,
                "total_lines": src_lines + test_lines,
                "test_ratio": round(test_lines / src_lines, 2) if src_lines > 0 else 0,
            },
            "storage": {
                "uploads_count": uploads_count,
                "recordings_count": recordings_count,
            },
        },
        "git": git_info,
    }
    
    # Добавляем метрики из API если доступен
    if include_api_metrics:
        try:
            import requests
            api_url = os.getenv("API_URL", "http://localhost:8000")
            response = requests.get(f"{api_url}/metrics", timeout=5)
            if response.status_code == 200:
                api_metrics = response.json()
                snapshot["metrics"]["api"] = api_metrics.get("storage", {})
                snapshot["metrics"]["database"] = api_metrics.get("database", {})
        except Exception:
            pass  # API недоступен, пропускаем
    
    # Добавляем OSINT метрики если доступны
    try:
        metrics_file = Path("cursor-metrics.json")
        if metrics_file.exists():
            file_metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
            osint_metrics = file_metrics.get("metrics", {}).get("osint")
            if osint_metrics:
                snapshot["metrics"]["osint"] = osint_metrics
    except Exception:
        pass
    
    return snapshot


def main():
    """Точка входа для скрипта."""
    logger.info("creating_metrics_snapshot")
    
    snapshot = create_snapshot()
    
    # Сохраняем в JSON
    output_file = Path("cursor-metrics.json")
    output_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    
    logger.info("metrics_snapshot_saved", path=str(output_file))
    
    print(f"✅ Metrics snapshot created: {output_file}")
    print(f"   Source lines: {snapshot['metrics']['code']['src_lines']}")
    print(f"   Test lines: {snapshot['metrics']['code']['test_lines']}")
    print(f"   Test ratio: {snapshot['metrics']['code']['test_ratio']}")
    print(f"   Uploads: {snapshot['metrics']['storage']['uploads_count']}")
    print(f"   Recordings: {snapshot['metrics']['storage']['recordings_count']}")


if __name__ == "__main__":
    main()

