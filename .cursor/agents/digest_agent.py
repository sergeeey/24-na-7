"""
Digest Agent — автоматическая генерация дайджестов.

Запускает генерацию дайджеста в указанное время (по умолчанию 22:50).
"""
import time
import subprocess
from pathlib import Path
from datetime import datetime, time as dt_time
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("agents.digest")


def generate_digest(date_str: str = "today") -> bool:
    """Генерирует дайджест для указанной даты."""
    try:
        logger.info("digest_generation_started", date=date_str)
        
        result = subprocess.run(
            ["python", "scripts/generate_digest.py", "--date", date_str],
            capture_output=True,
            timeout=300,
            text=True,
        )
        
        if result.returncode == 0:
            logger.info("digest_generated", date=date_str)
            return True
        else:
            logger.error("digest_generation_failed", error=result.stderr)
            return False
            
    except Exception as e:
        logger.error("digest_error", error=str(e))
        return False


def wait_until_time(target_hour: int = 22, target_minute: int = 50) -> None:
    """Ожидает до указанного времени."""
    while True:
        now = datetime.now()
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        
        if now >= target:
            target = target.replace(day=target.day + 1)
        
        seconds_until = (target - now).total_seconds()
        
        if seconds_until > 3600:  # Больше часа — ждём по часам
            logger.info("digest_agent_waiting", hours=seconds_until // 3600)
            time.sleep(3600)
        else:
            logger.info("digest_agent_final_wait", seconds=int(seconds_until))
            time.sleep(seconds_until)
            break


def main():
    """Основной цикл агента."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Digest Agent")
    parser.add_argument(
        "--time",
        default="22:50",
        help="Время генерации дайджеста (HH:MM)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Сгенерировать один раз и завершить",
    )
    parser.add_argument(
        "--date",
        default="today",
        help="Дата для дайджеста (today/yesterday/YYYY-MM-DD)",
    )
    
    args = parser.parse_args()
    
    if args.once:
        generate_digest(args.date)
    else:
        # Парсим время
        hour, minute = map(int, args.time.split(":"))
        
        logger.info("digest_agent_starting", time=args.time)
        
        while True:
            # Ждём до указанного времени
            wait_until_time(hour, minute)
            
            # Генерируем дайджест
            generate_digest("today")
            
            # Ждём до следующего дня
            time.sleep(60)


if __name__ == "__main__":
    main()













