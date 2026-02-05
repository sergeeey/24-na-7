"""
Metrics Agent — сбор и агрегация метрик системы.

Периодически собирает метрики и обновляет cursor-metrics.json.
"""
import time
import subprocess
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("agents.metrics")


def collect_metrics() -> bool:
    """Собирает метрики системы."""
    try:
        logger.info("metrics_collection_started")
        
        result = subprocess.run(
            ["python", "scripts/metrics_snapshot.py"],
            capture_output=True,
            timeout=60,
            text=True,
        )
        
        if result.returncode == 0:
            logger.info("metrics_collected")
            return True
        else:
            logger.error("metrics_collection_failed", error=result.stderr)
            return False
            
    except Exception as e:
        logger.error("metrics_error", error=str(e))
        return False


def main():
    """Основной цикл агента."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Metrics Agent")
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,  # 30 минут по умолчанию
        help="Интервал сбора метрик в секундах",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Собрать один раз и завершить",
    )
    
    args = parser.parse_args()
    
    logger.info("metrics_agent_starting", interval=args.interval, once=args.once)
    
    if args.once:
        collect_metrics()
    else:
        while True:
            collect_metrics()
            logger.info("metrics_agent_sleeping", seconds=args.interval)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()













