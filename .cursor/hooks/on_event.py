"""
Event-driven hooks для Reflexio 24/7.

Реагирует на события в проекте (изменение файлов, завершение задач и т.д.).
"""
import json
import subprocess
from pathlib import Path
from typing import Dict, List
from datetime import datetime

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("hooks")


def load_hooks_config() -> Dict:
    """Загружает конфигурацию хуков."""
    hooks_file = Path(".cursor/hooks/hooks.json")
    
    if not hooks_file.exists():
        logger.warning("hooks_config_not_found")
        return {"hooks": {}}
    
    try:
        return json.loads(hooks_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("hooks_config_load_failed", error=str(e))
        return {"hooks": {}}


def run_hook_script(script: str) -> bool:
    """Выполняет скрипт хука."""
    try:
        result = subprocess.run(
            script.split(),
            capture_output=True,
            timeout=60,
            text=True,
        )
        if result.returncode == 0:
            logger.info("hook_executed", script=script)
            return True
        else:
            logger.warning("hook_failed", script=script, error=result.stderr)
            return False
    except Exception as e:
        logger.error("hook_error", script=script, error=str(e))
        return False


def trigger_hook(hook_name: str, event_data: Dict = None) -> bool:
    """
    Триггерит выполнение хука.
    
    Args:
        hook_name: Имя хука из hooks.json
        event_data: Дополнительные данные события
        
    Returns:
        True если хук выполнен успешно
    """
    config = load_hooks_config()
    hooks = config.get("hooks", {})
    
    if hook_name not in hooks:
        logger.debug("hook_not_found", hook_name=hook_name)
        return False
    
    hook_config = hooks[hook_name]
    
    if not hook_config.get("enabled", False):
        logger.debug("hook_disabled", hook_name=hook_name)
        return False
    
    logger.info("hook_triggered", hook_name=hook_name)
    
    # Выполняем скрипты
    scripts = hook_config.get("scripts", [])
    if hook_config.get("action"):
        scripts.append(hook_config["action"])
    
    success = True
    for script in scripts:
        if not run_hook_script(script):
            success = False
    
    return success


def on_file_change(file_path: Path) -> None:
    """Обрабатывает изменение файла."""
    file_str = str(file_path)
    
    # Проверяем, какой хук нужно запустить
    if ".env" in file_str:
        trigger_hook("on_env_change")
    elif "mcp.json" in file_str or "profile.yaml" in file_str:
        trigger_hook("on_config_change")
    elif "audit_report.json" in file_str:
        trigger_hook("on_audit_complete")


def on_audit_complete() -> None:
    """Вызывается после завершения аудита."""
    trigger_hook("on_audit_complete")


def on_new_topic_detected(topic: str) -> None:
    """
    Обрабатывает обнаружение новой темы в транскрипциях.
    
    Args:
        topic: Обнаруженная тема
    """
    try:
        logger.info("new_topic_detected", topic=topic)
        
        # Импортируем модуль intelligence
        from src.mcp.intelligence import combined_search_and_scrape, save_to_memory_bank
        
        # Выполняем поиск и извлечение
        results = combined_search_and_scrape(topic, max_results=3, scrape_content=True)
        
        if results:
            # Сохраняем в Memory Bank
            save_to_memory_bank(topic, results)
            logger.info("topic_research_completed", topic=topic, results=len(results))
        else:
            logger.warning("topic_research_no_results", topic=topic)
            
    except Exception as e:
        logger.error("topic_research_failed", topic=topic, error=str(e))


def handle_event(event_name: str, payload: str = "") -> Dict:
    """
    Обрабатывает событие и запускает соответствующие хуки.
    
    Args:
        event_name: Имя события
        payload: Дополнительные данные события
        
    Returns:
        Результат обработки события
    """
    result = {"handled": False, "hook": None, "action": None}
    
    # Маппинг событий на хуки
    event_to_hook = {
        "low_confidence_detected": "on_low_confidence",
        "audit_success": "on_audit_success",
        "mcp_degraded": "on_mcp_degraded",
        "new_topic_detected": "new_topic_detected",
    }
    
    hook_name = event_to_hook.get(event_name)
    
    if not hook_name:
        logger.warning("unknown_event", event=event_name)
        return result
    
    if hook_name == "new_topic_detected" and payload:
        on_new_topic_detected(payload)
        result["handled"] = True
        result["hook"] = hook_name
        result["action"] = "OSINT mission triggered"
    else:
        success = trigger_hook(hook_name)
        result["handled"] = success
        result["hook"] = hook_name
    
    return result


def main():
    """Точка входа для CLI."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python .cursor/hooks/on_event.py <event_name> [payload]")
        print("\nAvailable events:")
        print("  - low_confidence_detected [message]")
        print("  - audit_success")
        print("  - mcp_degraded")
        print("  - new_topic_detected [topic]")
        sys.exit(1)
    
    event_name = sys.argv[1]
    payload = sys.argv[2] if len(sys.argv) > 2 else ""
    
    result = handle_event(event_name, payload)
    
    if result["handled"]:
        print(f"✅ Event '{event_name}' handled by hook '{result['hook']}'")
        if result.get("action"):
            print(f"   Action: {result['action']}")
    else:
        print(f"⚠️  Event '{event_name}' not handled (no hook or hook disabled)")
    
    return 0 if result["handled"] else 1


if __name__ == "__main__":
    main()

