"""
Проверка готовности к запуску OSINT миссий.

Проверяет наличие API ключей, конфигурации и всех необходимых компонентов.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def check_env_file():
    """Проверяет наличие .env файла и API ключей."""
    env_file = Path(".env")
    
    if not env_file.exists():
        print("⚠️  .env файл не найден")
        print("   Создайте .env файл с API ключами:")
        print("   BRAVE_API_KEY=your_key")
        print("   BRIGHTDATA_API_KEY=your_key")
        return False
    
    try:
        content = env_file.read_text(encoding="utf-8")
        
        has_brave = "BRAVE_API_KEY" in content and not content.count("BRAVE_API_KEY=") == content.count("BRAVE_API_KEY=your_key")
        
        # Bright Data: проверяем либо API key, либо proxy
        has_bright_key = "BRIGHTDATA_API_KEY" in content and not content.count("BRIGHTDATA_API_KEY=") == content.count("BRIGHTDATA_API_KEY=your_key")
        has_bright_proxy = "BRIGHTDATA_PROXY_HTTP" in content and "brd.superproxy.io" in content
        
        has_bright = has_bright_key or has_bright_proxy
        
        if has_brave:
            print("✅ BRAVE_API_KEY найден в .env")
        else:
            print("⚠️  BRAVE_API_KEY не найден или не настроен в .env")
        
        if has_bright_proxy:
            print("✅ BRIGHTDATA_PROXY_HTTP найден в .env")
        elif has_bright_key:
            print("✅ BRIGHTDATA_API_KEY найден в .env")
        else:
            print("⚠️  BRIGHTDATA_API_KEY или BRIGHTDATA_PROXY_HTTP не найден в .env")
        
        return has_brave and has_bright
        
    except Exception as e:
        print(f"❌ Ошибка чтения .env: {e}")
        return False


def check_missions():
    """Проверяет наличие миссий."""
    missions_dir = Path(".cursor/osint/missions")
    
    if not missions_dir.exists():
        print("⚠️  Директория миссий не найдена")
        missions_dir.mkdir(parents=True, exist_ok=True)
        print("   Создана директория: .cursor/osint/missions")
        return False
    
    mission_files = list(missions_dir.glob("*.json"))
    
    if mission_files:
        print(f"✅ Найдено миссий: {len(mission_files)}")
        for mf in mission_files[:3]:
            print(f"   - {mf.name}")
        return True
    else:
        print("⚠️  Миссии не найдены")
        print("   Используйте example_mission.json как шаблон")
        return False


def check_modules():
    """Проверяет доступность модулей OSINT."""
    modules = [
        "src.osint.collector",
        "src.osint.contextor",
        "src.osint.pemm_agent",
        "src.osint.deepconf",
        "src.mcp.clients",
    ]
    
    all_ok = True
    
    for module_name in modules:
        try:
            __import__(module_name)
            print(f"✅ Модуль {module_name} доступен")
        except ImportError as e:
            print(f"❌ Модуль {module_name} не найден: {e}")
            all_ok = False
    
    return all_ok


def check_directories():
    """Проверяет наличие необходимых директорий."""
    dirs = [
        Path(".cursor/osint/results"),
        Path(".cursor/memory"),
    ]
    
    all_ok = True
    
    for dir_path in dirs:
        if not dir_path.exists():
            print(f"⚠️  Директория не найдена: {dir_path}")
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"   Создана: {dir_path}")
        else:
            print(f"✅ Директория существует: {dir_path}")
    
    return all_ok


def main():
    """Основная функция проверки."""
    print("\n" + "=" * 70)
    print("OSINT Mission Readiness Check")
    print("=" * 70)
    print()
    
    checks = [
        ("Environment Variables", check_env_file),
        ("Missions", check_missions),
        ("OSINT Modules", check_modules),
        ("Directories", check_directories),
    ]
    
    results = {}
    
    for name, check_func in checks:
        print(f"\n[{name}]")
        print("-" * 70)
        results[name] = check_func()
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    all_passed = all(results.values())
    
    if all_passed:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
        print("\nСистема готова к запуску OSINT миссий.")
        print("\nЗапустите:")
        print("  @playbook osint-mission --mission_file .cursor/osint/missions/example_mission.json")
        return 0
    else:
        print("⚠️  ЕСТЬ ПРОБЛЕМЫ")
        print("\nИсправьте указанные проблемы перед запуском миссий.")
        
        if not results.get("Environment Variables"):
            print("\nВАЖНО: Настройте API ключи в .env файле")
        
        return 1


if __name__ == "__main__":
    sys.exit(main())

