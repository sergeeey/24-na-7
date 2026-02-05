"""
SAFE+CoVe Validation Framework для Reflexio 24/7.

SAFE (Security And Functionality Evaluation) — проверки безопасности и функциональности.
CoVe (Chain of Verification) — проверки логической согласованности.
"""
import os
import sys
import argparse
import json
from pathlib import Path
from typing import List, Tuple, Dict

# Попытка загрузить настройки
try:
    from src.utils.config import settings
except ImportError:
    settings = None


def check_pii_mask() -> Tuple[bool, str]:
    """
    SAFE-1: Проверка настройки PII-маскирования.
    
    Returns:
        (is_valid, message)
    """
    if settings:
        pii_mask = getattr(settings, "PII_MASK", None) or os.getenv("PII_MASK")
        if pii_mask and str(pii_mask).lower() in ("true", "1", "yes"):
            return True, "PII маскирование включено"
        else:
            return False, "⚠️ PII маскирование не настроено (рекомендуется включить)"
    else:
        # Проверяем через env напрямую
        if os.getenv("PII_MASK", "").lower() in ("true", "1", "yes"):
            return True, "PII маскирование включено"
        else:
            return False, "⚠️ PII_MASK не установлен в .env"


def check_zero_retention() -> Tuple[bool, str]:
    """
    SAFE-2: Проверка zero-retention режима.
    
    Returns:
        (is_valid, message)
    """
    if settings:
        zero_retention = getattr(settings, "ZERO_RETENTION", None) or os.getenv("ZERO_RETENTION")
        if zero_retention and str(zero_retention).lower() in ("true", "1", "yes"):
            return True, "Zero-retention режим включен"
        else:
            return False, "⚠️ Zero-retention не включен (рекомендуется для приватности)"
    else:
        if os.getenv("ZERO_RETENTION", "").lower() in ("true", "1", "yes"):
            return True, "Zero-retention режим включен"
        else:
            return False, "ZERO_RETENTION не установлен в .env"


def check_env_file() -> Tuple[bool, str]:
    """
    SAFE-3: Проверка наличия .env файла и .env.example.
    
    Returns:
        (is_valid, message)
    """
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if not env_file.exists():
        return False, "❌ .env файл отсутствует (создайте из .env.example)"
    
    if not env_example.exists():
        return False, "⚠️ .env.example отсутствует (рекомендуется добавить)"
    
    # Проверяем, что .env не в git
    gitignore = Path(".gitignore")
    if gitignore.exists():
        gitignore_content = gitignore.read_text(encoding="utf-8")
        if ".env" in gitignore_content:
            return True, ".env настроен корректно (не в git)"
    
    return True, ".env найден"


def check_storage_directories() -> Tuple[bool, str]:
    """
    SAFE-4: Проверка директорий хранения.
    
    Returns:
        (is_valid, message)
    """
    required_dirs = [
        "src/storage/uploads",
        "src/storage/recordings",
    ]
    
    missing = []
    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            missing.append(dir_path)
    
    if missing:
        return False, f"❌ Отсутствуют директории: {', '.join(missing)}"
    
    return True, "Все директории хранения существуют"


def check_api_security() -> Tuple[bool, str]:
    """
    SAFE-5: Проверка базовых настроек безопасности API.
    
    Returns:
        (is_valid, message)
    """
    # Проверяем, что API не слушает на 0.0.0.0 в продакшене (если есть индикатор)
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_url = os.getenv("API_URL", "")
    
    if "0.0.0.0" in api_host and "localhost" not in api_url.lower():
        return False, "⚠️ API слушает на 0.0.0.0 (проверьте настройки для продакшена)"
    
    return True, "Настройки API безопасности базовые"


def check_database_exists() -> Tuple[bool, str]:
    """
    CoVe-1: Проверка наличия базы данных.
    
    Returns:
        (is_valid, message)
    """
    db_path = Path("src/storage/reflexio.db")
    
    if db_path.exists():
        return True, "База данных существует"
    else:
        return False, "⚠️ База данных не инициализирована (запустите db_init.py)"


def check_schema_consistency() -> Tuple[bool, str]:
    """
    CoVe-2: Проверка согласованности схемы БД.
    
    Returns:
        (is_valid, message)
    """
    schema_file = Path("schema.sql")
    
    if not schema_file.exists():
        return False, "⚠️ schema.sql отсутствует"
    
    # Простая проверка наличия ключевых таблиц в схеме
    schema_content = schema_file.read_text(encoding="utf-8")
    required_tables = ["ingest_queue", "transcriptions", "facts"]
    
    missing_tables = []
    for table in required_tables:
        # Проверяем наличие CREATE TABLE с именем таблицы (case-insensitive)
        if f"CREATE TABLE" in schema_content.upper() and table.lower() in schema_content.lower():
            continue
        missing_tables.append(table)
    
    if missing_tables:
        return False, f"⚠️ В схеме отсутствуют таблицы: {', '.join(missing_tables)}"
    
    return True, "Схема БД согласована"


def check_dependencies() -> Tuple[bool, str]:
    """
    CoVe-3: Проверка наличия ключевых зависимостей.
    
    Returns:
        (is_valid, message)
    """
    missing = []
    
    try:
        import fastapi
    except ImportError:
        missing.append("fastapi")
    
    try:
        import webrtcvad
    except ImportError:
        missing.append("webrtcvad")
    
    try:
        import sounddevice
    except ImportError:
        missing.append("sounddevice")
    
    try:
        import faster_whisper
    except ImportError:
        missing.append("faster-whisper")
    
    try:
        import librosa
    except ImportError:
        # librosa опционален (для фильтра)
        pass
    
    if missing:
        return False, f"❌ Отсутствуют зависимости: {', '.join(missing)}"
    
    return True, "Все ключевые зависимости установлены"


def check_api_endpoints() -> Tuple[bool, str]:
    """
    CoVe-4: Проверка работоспособности API endpoints.
    
    Returns:
        (is_valid, message)
    """
    try:
        import requests
        api_url = os.getenv("API_URL", "http://localhost:8000")
        response = requests.get(f"{api_url}/health", timeout=5)
        if response.status_code == 200:
            return True, "API endpoints доступны"
        else:
            return False, f"⚠️ API вернул код {response.status_code}"
    except requests.exceptions.RequestException:
        return False, "⚠️ API недоступен (возможно, сервер не запущен)"
    except ImportError:
        return False, "⚠️ requests не установлен (не удаётся проверить API)"


def check_schema_validation() -> Tuple[bool, str]:
    """
    SAFE-6: Проверка валидности конфигурационных файлов.
    
    Returns:
        (is_valid, message)
    """
    issues = []
    
    # Проверяем mcp.json
    mcp_path = Path(".cursor/mcp.json")
    if mcp_path.exists():
        try:
            mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
            if not isinstance(mcp_data, dict):
                issues.append("mcp.json не является объектом")
        except json.JSONDecodeError as e:
            issues.append(f"mcp.json невалиден: {str(e)}")
    
    # Проверяем hooks.json
    hooks_path = Path(".cursor/hooks/hooks.json")
    if hooks_path.exists():
        try:
            hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
            if not isinstance(hooks_data, dict):
                issues.append("hooks.json не является объектом")
        except json.JSONDecodeError as e:
            issues.append(f"hooks.json невалиден: {str(e)}")
    
    if issues:
        return False, f"⚠️ Проблемы с конфигурацией: {'; '.join(issues)}"
    
    return True, "Конфигурационные файлы валидны"


def run_validation(check_type: str = "all") -> Dict:
    """
    Запускает валидацию.
    
    Args:
        check_type: "all", "safe", "cove"
        
    Returns:
        Словарь с результатами валидации
    """
    results = {
        "safe_checks": [],
        "cove_checks": [],
        "total_passed": 0,
        "total_failed": 0,
    }
    
    # SAFE проверки
    if check_type in ("all", "safe"):
        safe_checks = [
            ("PII Mask", check_pii_mask),
            ("Zero Retention", check_zero_retention),
            ("Environment Files", check_env_file),
            ("Storage Directories", check_storage_directories),
            ("API Security", check_api_security),
            ("Schema Validation", check_schema_validation),
        ]
        
        for name, check_func in safe_checks:
            is_valid, message = check_func()
            results["safe_checks"].append({
                "name": name,
                "valid": is_valid,
                "message": message,
            })
            if is_valid:
                results["total_passed"] += 1
            else:
                results["total_failed"] += 1
    
    # CoVe проверки
    if check_type in ("all", "cove"):
        cove_checks = [
            ("Database Exists", check_database_exists),
            ("Schema Consistency", check_schema_consistency),
            ("Dependencies", check_dependencies),
            ("API Endpoints", check_api_endpoints),
        ]
        
        for name, check_func in cove_checks:
            is_valid, message = check_func()
            results["cove_checks"].append({
                "name": name,
                "valid": is_valid,
                "message": message,
            })
            if is_valid:
                results["total_passed"] += 1
            else:
                results["total_failed"] += 1
    
    return results


def main():
    """Точка входа для CLI."""
    parser = argparse.ArgumentParser(description="SAFE+CoVe Validation Framework")
    parser.add_argument(
        "--check",
        choices=["all", "safe", "cove"],
        default="all",
        help="Тип проверки",
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("SAFE+CoVe Validation Framework — Reflexio 24/7")
    print("=" * 70)
    print()
    
    results = run_validation(args.check)
    
    # Выводим результаты
    if results["safe_checks"]:
        print("🔒 SAFE Checks (Security & Functionality):")
        print()
        for check in results["safe_checks"]:
            status = "✅" if check["valid"] else "❌"
            print(f"  {status} {check['name']}: {check['message']}")
        print()
    
    if results["cove_checks"]:
        print("🔗 CoVe Checks (Chain of Verification):")
        print()
        for check in results["cove_checks"]:
            status = "✅" if check["valid"] else "❌"
            print(f"  {status} {check['name']}: {check['message']}")
        print()
    
    # Итог
    total = results["total_passed"] + results["total_failed"]
    print("=" * 70)
    print(f"Итог: {results['total_passed']}/{total} проверок пройдено")
    
    if results["total_failed"] == 0:
        print("✅ Все проверки пройдены успешно!")
        return 0
    else:
        print(f"⚠️  Обнаружено {results['total_failed']} проблем")
        return 1


if __name__ == "__main__":
    sys.exit(main())

