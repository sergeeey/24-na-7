"""Настройка логирования с structlog."""
import sys
import structlog
from structlog.types import Processor
from pathlib import Path

from .config import settings


def setup_logging() -> None:
    """Настраивает structlog для проекта."""
    
    # Процессоры для форматирования
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]
    
    # Выбираем рендерер в зависимости от окружения
    if settings.LOG_LEVEL == "DEBUG":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(
            structlog.processors.JSONRenderer()
        )
    
    # Маппинг уровней логирования
    log_level_map = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50,
    }
    min_level = log_level_map.get(settings.LOG_LEVEL.upper(), 20)
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(min_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "reflexio"):
    """Возвращает настроенный logger."""
    return structlog.get_logger(name)

