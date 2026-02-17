"""
Validation Agent — автоматические SAFE+CoVe проверки.

Периодически запускает валидацию и отчёты о проблемах.
"""
import time
import subprocess
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("agents.validation")


def run_validation() -> bool:
    """Запускает SAFE+CoVe валидацию."""
    try:
        logger.info("validation_started")
        
        result = subprocess.run(
            ["python", ".cursor/validation/validators.py", "--check", "all"],
            capture_output=True,
            timeout=60,
            text=True,
        )
        
        if result.returncode == 0:
            logger.info("validation_passed")
            return True
        else:
            logger.warning("validation_failed", details=result.stdout)
            return False
            
    except Exception as e:
        logger.error("validation_error", error=str(e))
        return False


def main():
    """Основной цикл агента."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validation Agent")
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,  # 1 час по умолчанию
        help="Интервал валидации в секундах",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Выполнить один раз и завершить",
    )
    
    args = parser.parse_args()
    
    logger.info("validation_agent_starting", interval=args.interval, once=args.once)
    
    if args.once:
        run_validation()
    else:
        while True:
            run_validation()
            logger.info("validation_agent_sleeping", seconds=args.interval)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()













