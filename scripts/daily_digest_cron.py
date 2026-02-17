"""
Вечерний cron для генерации и отправки дайджеста (22:50).
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import sys
import time
from pathlib import Path
from datetime import datetime, date, time as dt_time
import argparse

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.digest.generator import DigestGenerator
from src.utils.logging import setup_logging, get_logger
from src.utils.process_lock import ProcessLock, ProcessLockError

setup_logging()
logger = get_logger("cron.daily_digest")


def wait_until_time(target_hour: int = 22, target_minute: int = 50):
    """Ждёт до указанного времени."""
    while True:
        now = datetime.now()
        target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        
        if now >= target_time:
            # Если время уже прошло, планируем на завтра
            target_time = target_time.replace(day=target_time.day + 1)
        
        seconds_until = (target_time - now).total_seconds()
        
        if seconds_until > 0:
            logger.info(
                "waiting_for_digest_time",
                target_time=target_time.strftime("%Y-%m-%d %H:%M:%S"),
                seconds_until=int(seconds_until),
            )
            time.sleep(min(seconds_until, 3600))  # Максимум 1 час за раз
        else:
            break


def generate_and_send_digest(target_date: date = None, send_telegram: bool = True):
    """
    Генерирует дайджест и отправляет в Telegram.

    Args:
        target_date: Дата для дайджеста (если None, используется сегодня)
        send_telegram: Отправлять ли в Telegram

    Returns:
        True если успешно, False при ошибке

    Raises:
        ProcessLockError: Если другой process уже генерирует дайджест
    """
    if target_date is None:
        target_date = date.today()

    # Acquire process lock — prevent duplicate execution
    try:
        with ProcessLock("daily_digest", timeout=10):
            logger.info("daily_digest_started", date=target_date.isoformat())

            try:
                # Генерируем дайджест
                generator = DigestGenerator()

                # Генерируем markdown и PDF
                md_file = generator.generate(
                    target_date=target_date,
                    output_format="markdown",
                    include_metadata=True,
                )

                pdf_file = generator.generate(
                    target_date=target_date,
                    output_format="pdf",
                    include_metadata=True,
                )

                logger.info(
                    "digest_generated",
                    date=target_date.isoformat(),
                    markdown_file=str(md_file),
                    pdf_file=str(pdf_file),
                )

                # Отправляем в Telegram если нужно
                if send_telegram:
                    try:
                        from src.digest.telegram_sender import TelegramDigestSender
                        sender = TelegramDigestSender()
                        sender.send_digest(target_date, md_file, pdf_file)
                        logger.info("digest_sent_to_telegram", date=target_date.isoformat())
                    except ImportError:
                        logger.warning("telegram_sender_not_available", fallback="skip")
                    except Exception as e:
                        logger.error("telegram_send_failed", error=str(e))

                return True

            except Exception as e:
                logger.error("daily_digest_failed", date=target_date.isoformat(), error=str(e))
                return False

    except ProcessLockError as e:
        logger.warning(
            "daily_digest_already_running",
            date=target_date.isoformat(),
            message=str(e),
        )
        return False  # Graceful exit — another process is running


def main():
    """Основная функция."""
    parser = argparse.ArgumentParser(description="Daily Digest Cron (22:50)")
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
        default=None,
        help="Дата для дайджеста (today/yesterday/YYYY-MM-DD). Если не указано, используется сегодня.",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Не отправлять в Telegram",
    )
    
    args = parser.parse_args()
    
    # Парсим дату
    target_date = None
    if args.date:
        if args.date == "today":
            target_date = date.today()
        elif args.date == "yesterday":
            from datetime import timedelta
            target_date = date.today() - timedelta(days=1)
        else:
            try:
                target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            except ValueError:
                logger.error("invalid_date_format", date=args.date)
                sys.exit(1)
    
    if args.once:
        # Генерируем один раз
        generate_and_send_digest(target_date, send_telegram=not args.no_telegram)
    else:
        # Парсим время
        hour, minute = map(int, args.time.split(":"))
        
        logger.info("daily_digest_cron_started", time=args.time)
        
        while True:
            # Ждём до указанного времени
            wait_until_time(hour, minute)
            
            # Генерируем дайджест
            generate_and_send_digest(send_telegram=not args.no_telegram)
            
            # Ждём минуту перед следующей проверкой
            time.sleep(60)


if __name__ == "__main__":
    main()





