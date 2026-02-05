#!/usr/bin/env python3
"""
Проверка API ключей для Reflexio 24/7.
Проверяет оба "мира": Python-приложение (.env) и MCP конфигурацию.
"""
import sys
import json
import os
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

report = {
    "timestamp": None,
    "python_env": {},
    "mcp_config": {},
    "status": "pending",
    "issues": [],
    "warnings": [],
}


def check_python_env() -> Dict[str, Any]:
    """Проверка Python .env файла."""
    result = {
        "status": "unknown",
        "env_file_exists": False,
        "keys": {},
        "issues": [],
    }
    
    env_file = Path(".env")
    result["env_file_exists"] = env_file.exists()
    
    if not env_file.exists():
        result["status"] = "error"
        result["issues"].append("Файл .env не найден в корне проекта")
        return result
    
    # Читаем .env вручную для проверки
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        env_vars = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")  # Убираем кавычки
                env_vars[key] = value
        
        # Проверяем ключевые переменные
        required_keys = [
            "DB_BACKEND",
            "SUPABASE_URL",
            "SUPABASE_ANON_KEY",
            "LLM_PROVIDER",
        ]
        
        optional_keys = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "BRAVE_API_KEY",
            "BRIGHTDATA_API_KEY",
            "BRIGHTDATA_PROXY_HTTP",
            "SUPABASE_SERVICE_ROLE",
        ]
        
        for key in required_keys:
            if key in env_vars and env_vars[key]:
                result["keys"][key] = {
                    "exists": True,
                    "value_preview": f"{env_vars[key][:10]}..." if len(env_vars[key]) > 10 else env_vars[key],
                }
            else:
                result["keys"][key] = {"exists": False}
                result["issues"].append(f"Отсутствует обязательная переменная: {key}")
        
        for key in optional_keys:
            if key in env_vars and env_vars[key]:
                result["keys"][key] = {
                    "exists": True,
                    "value_preview": f"{env_vars[key][:10]}..." if len(env_vars[key]) > 10 else env_vars[key],
                }
            else:
                result["keys"][key] = {"exists": False}
        
        # Проверяем загрузку через settings
        try:
            from src.utils.config import settings
            settings_dict = settings.model_dump()
            
            # Проверяем что ключевые значения загрузились
            loaded_ok = True
            for key in ["SUPABASE_URL", "DB_BACKEND"]:
                if not getattr(settings, key, None):
                    loaded_ok = False
                    result["issues"].append(f"Переменная {key} не загрузилась через settings (проверьте src/utils/config.py)")
            
            if loaded_ok:
                result["settings_loaded"] = True
            else:
                result["settings_loaded"] = False
                
        except Exception as e:
            result["settings_loaded"] = False
            result["issues"].append(f"Ошибка загрузки через settings: {e}")
        
        # Определяем статус
        if result["issues"]:
            result["status"] = "error"
        elif all(result["keys"].get(k, {}).get("exists") for k in required_keys):
            result["status"] = "ok"
        else:
            result["status"] = "warn"
            
    except Exception as e:
        result["status"] = "error"
        result["issues"].append(f"Ошибка чтения .env: {e}")
    
    return result


def check_mcp_config() -> Dict[str, Any]:
    """Проверка MCP конфигурации."""
    result = {
        "status": "unknown",
        "mcp_file_exists": False,
        "servers": {},
        "issues": [],
        "warnings": [],
    }
    
    mcp_file = Path(".cursor/mcp.json")
    result["mcp_file_exists"] = mcp_file.exists()
    
    if not mcp_file.exists():
        result["status"] = "error"
        result["issues"].append("Файл .cursor/mcp.json не найден")
        return result
    
    try:
        mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
        mcp_servers = mcp_data.get("mcpServers", {})
        
        # Проверяем ключевые серверы
        key_servers = ["brave", "brightdata"]
        
        for server_name in key_servers:
            server_config = mcp_servers.get(server_name, {})
            
            server_info = {
                "exists": server_name in mcp_servers,
                "enabled": server_config.get("enabled", False),
                "has_command": "command" in server_config,
                "has_url": "url" in server_config,
                "has_api_key_env": "api_key_env" in server_config,
            }
            
            # Проверяем что сервер настроен правильно
            if not server_info["exists"]:
                result["warnings"].append(f"MCP сервер '{server_name}' не найден в mcp.json")
            elif not server_info["enabled"]:
                result["warnings"].append(f"MCP сервер '{server_name}' отключен (enabled: false)")
            
            # Проверяем наличие переменных окружения (в системных, не в .env!)
            # ВАЖНО: MCP серверы Cursor читают только системные переменные или настройки Cursor
            if server_name == "brave" and server_info["enabled"]:
                brave_key = os.getenv("BRAVE_API_KEY")
                if not brave_key:
                    result["warnings"].append(
                        "⚠️  BRAVE_API_KEY не найдена в системных переменных окружения. "
                        "MCP серверы Cursor НЕ читают .env проекта! "
                        "Настройте в Cursor Settings → MCP или задайте системную переменную."
                    )
                else:
                    server_info["api_key_found"] = True
            
            if server_name == "brightdata" and server_info["enabled"]:
                bright_key = os.getenv("BRIGHTDATA_API_KEY")
                bright_proxy = os.getenv("BRIGHTDATA_PROXY_HTTP")
                bright_proxy_ws = os.getenv("BRIGHTDATA_PROXY_WS")
                
                has_config = bright_key or bright_proxy or bright_proxy_ws
                if not has_config:
                    result["warnings"].append(
                        "⚠️  BRIGHTDATA_API_KEY, BRIGHTDATA_PROXY_HTTP или BRIGHTDATA_PROXY_WS не найдены в системных переменных. "
                        "MCP серверы Cursor НЕ читают .env проекта! "
                        "Настройте в Cursor Settings → MCP или задайте системную переменную."
                    )
                else:
                    server_info["api_key_found"] = True
                    server_info["config_type"] = "api_key" if bright_key else ("proxy_http" if bright_proxy else "proxy_ws")
            
            result["servers"][server_name] = server_info
        
        # Определяем статус
        if result["issues"]:
            result["status"] = "error"
        elif result["warnings"]:
            result["status"] = "warn"
        else:
            result["status"] = "ok"
            
    except json.JSONDecodeError as e:
        result["status"] = "error"
        result["issues"].append(f"Ошибка парсинга JSON: {e}")
    except Exception as e:
        result["status"] = "error"
        result["issues"].append(f"Ошибка чтения mcp.json: {e}")
    
    return result


def main():
    """Основная функция."""
    from datetime import datetime
    
    report["timestamp"] = datetime.now().isoformat()
    
    print("\n" + "=" * 70)
    print("🔑 Проверка API ключей — Reflexio 24/7")
    print("=" * 70)
    print()
    
    # Проверка 1: Python .env
    print("[PYTHON .ENV]")
    python_result = check_python_env()
    report["python_env"] = python_result
    
    if python_result["status"] == "ok":
        print("✅ Python .env: OK")
        print(f"   Файл найден: {python_result['env_file_exists']}")
        print(f"   Загружено через settings: {python_result.get('settings_loaded', False)}")
        
        # Показываем существующие ключи
        existing_keys = [k for k, v in python_result["keys"].items() if v.get("exists")]
        print(f"   Найдено ключей: {len(existing_keys)}")
        print(f"   Ключи: {', '.join(existing_keys)}")
    elif python_result["status"] == "warn":
        print("⚠️  Python .env: WARNING")
        for issue in python_result["issues"]:
            print(f"   ⚠️  {issue}")
    else:
        print("❌ Python .env: ERROR")
        for issue in python_result["issues"]:
            print(f"   ❌ {issue}")
    
    print()
    
    # Проверка 2: MCP конфигурация
    print("[MCP CONFIG]")
    mcp_result = check_mcp_config()
    report["mcp_config"] = mcp_result
    
    if mcp_result["status"] == "ok":
        print("✅ MCP конфигурация: OK")
        print(f"   Файл найден: {mcp_result['mcp_file_exists']}")
        
        for server_name, server_info in mcp_result["servers"].items():
            status_icon = "✅" if server_info["enabled"] else "⚠️"
            print(f"   {status_icon} {server_name}: {'включён' if server_info['enabled'] else 'отключён'}")
    elif mcp_result["status"] == "warn":
        print("⚠️  MCP конфигурация: WARNING")
        for warning in mcp_result["warnings"]:
            print(f"   ⚠️  {warning}")
    else:
        print("❌ MCP конфигурация: ERROR")
        for issue in mcp_result["issues"]:
            print(f"   ❌ {issue}")
    
    print()
    
    # Собираем все проблемы
    all_issues = python_result.get("issues", []) + mcp_result.get("issues", [])
    all_warnings = python_result.get("warnings", []) + mcp_result.get("warnings", [])
    
    report["issues"] = all_issues
    report["warnings"] = all_warnings
    
    # Определяем общий статус
    if all_issues:
        report["status"] = "error"
    elif all_warnings:
        report["status"] = "warn"
    else:
        report["status"] = "ok"
    
    # Сохраняем отчёт
    report_path = Path(".cursor/audit/api_keys_check.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # Итоги
    print("=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    
    if report["status"] == "ok":
        print("✅ Все API ключи настроены корректно!")
    elif report["status"] == "warn":
        print("⚠️  Есть предупреждения (см. выше)")
        print("\n💡 Важно:")
        print("   - MCP серверы Cursor НЕ читают .env проекта")
        print("   - Настройте ключи в Cursor Settings → MCP")
        print("   - Или задайте системные переменные окружения")
    else:
        print("❌ Обнаружены ошибки!")
        print("\n💡 Рекомендации:")
        print("   1. Создайте .env в корне проекта")
        print("   2. Заполните обязательные переменные")
        print("   3. Настройте MCP ключи в Cursor Settings → MCP")
        print("   4. Перезагрузите окно редактора (Reload Window)")
    
    print(f"\n📄 Отчёт сохранён: {report_path}")
    print("=" * 70)
    print()
    
    # Дополнительная информация
    if all_warnings:
        print("📖 Подробнее: см. API_KEYS_SETUP.md")
        print()
    
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

