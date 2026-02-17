"""
Audit Agent — автоматический запуск CEB-E аудита.

Работает как фоновый процесс, запускает аудит по расписанию или при событиях.
"""
import time
import subprocess
from pathlib import Path
from datetime import datetime
import sys

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("agents.audit")


def run_audit() -> bool:
    """Запускает CEB-E аудит."""
    try:
        logger.info("audit_triggered")
        
        result = subprocess.run(
            ["python", ".cursor/audit/run_audit.py", "--mode", "standard"],
            capture_output=True,
            timeout=300,
            text=True,
        )
        
        if result.returncode == 0:
            logger.info("audit_completed")
            
            # Триггерим хук после завершения аудита
            try:
                from .cursor.hooks.on_event import on_audit_complete
                on_audit_complete()
            except Exception:
                pass
            
            return True
        else:
            logger.error("audit_failed", error=result.stderr)
            return False
            
    except Exception as e:
        logger.error("audit_error", error=str(e))
        return False


def main():
    """Основной цикл агента."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Audit Agent")
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,  # 1 час по умолчанию
        help="Интервал запуска аудита в секундах",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Запустить один раз и завершить",
    )
    
    args = parser.parse_args()
    
    logger.info("audit_agent_starting", interval=args.interval, once=args.once)
    
    if args.once:
        run_audit()
    else:
        # Бесконечный цикл
        while True:
            run_audit()
            logger.info("audit_agent_sleeping", seconds=args.interval)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()













