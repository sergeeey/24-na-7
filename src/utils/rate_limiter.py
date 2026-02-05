"""
Rate Limiting для Reflexio 24/7 API.
Защита от DDoS и abuse.
"""
import os
from typing import Optional

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.utils.logging import get_logger

logger = get_logger("rate_limiter")


class RateLimitConfig:
    """Конфигурация rate limiting."""
    
    # Лимиты по умолчанию
    DEFAULT_LIMIT: str = "100/minute"
    
    # Специфичные лимиты для endpoints
    INGEST_AUDIO_LIMIT: str = "10/minute"  # Загрузка аудио
    TRANSCRIBE_LIMIT: str = "30/minute"    # Транскрибация
    DIGEST_LIMIT: str = "60/minute"        # Дайджесты
    HEALTH_LIMIT: str = "200/minute"       # Health checks (больше)
    
    # Burst размер (на сколько запросов можно превысить)
    BURST_SIZE: int = 5
    
    # Storage backend
    STORAGE_URI: Optional[str] = os.getenv("REDIS_URL", "memory://")


def create_limiter() -> Limiter:
    """
    Создает и конфигурирует Limiter.
    
    Returns:
        Настроенный экземпляр Limiter
    """
    storage_uri = RateLimitConfig.STORAGE_URI
    
    if storage_uri.startswith("redis://"):
        logger.info("rate_limiter_using_redis", uri=storage_uri)
    else:
        logger.info("rate_limiter_using_memory", note="not_suitable_for_production")
    
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[RateLimitConfig.DEFAULT_LIMIT],
        storage_uri=storage_uri,
        strategy="fixed-window",  # Можно изменить на "moving-window" для точности
        enabled=True,
        swallow_errors=False,  # Не скрывать ошибки rate limiting
        headers_enabled=True,  # Добавлять X-RateLimit-* заголовки
    )
    
    return limiter


def get_limit_for_endpoint(endpoint_name: str) -> str:
    """
    Возвращает лимит для конкретного endpoint.
    
    Args:
        endpoint_name: Имя endpoint (например, "ingest_audio")
        
    Returns:
        Строка с лимитом (например, "10/minute")
    """
    limits = {
        "ingest_audio": RateLimitConfig.INGEST_AUDIO_LIMIT,
        "transcribe": RateLimitConfig.TRANSCRIBE_LIMIT,
        "digest": RateLimitConfig.DIGEST_LIMIT,
        "health": RateLimitConfig.HEALTH_LIMIT,
    }
    
    return limits.get(endpoint_name, RateLimitConfig.DEFAULT_LIMIT)


def setup_rate_limiting(app) -> Limiter:
    """
    Настраивает rate limiting для FastAPI приложения.
    
    Args:
        app: FastAPI приложение
        
    Returns:
        Настроенный Limiter
    """
    limiter = create_limiter()
    
    # Добавляем middleware
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    
    # Обработчик превышения лимита
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request, exc):
        client_ip = get_remote_address(request)
        endpoint = request.url.path
        
        logger.warning(
            "rate_limit_exceeded",
            client_ip=client_ip,
            endpoint=endpoint,
            method=request.method,
        )
        
        return _rate_limit_exceeded_handler(request, exc)
    
    logger.info("rate_limiting_configured")
    return limiter


# Декораторы для удобного использования
def limit_ingest():
    """Декоратор для лимитирования загрузки аудио."""
    from slowapi.util import get_limiter
    
    def decorator(func):
        return get_limiter().limit(RateLimitConfig.INGEST_AUDIO_LIMIT)(func)
    return decorator


def limit_transcribe():
    """Декоратор для лимитирования транскрибации."""
    from slowapi.util import get_limiter
    
    def decorator(func):
        return get_limiter().limit(RateLimitConfig.TRANSCRIBE_LIMIT)(func)
    return decorator


def limit_digest():
    """Декоратор для лимитирования дайджестов."""
    from slowapi.util import get_limiter
    
    def decorator(func):
        return get_limiter().limit(RateLimitConfig.DIGEST_LIMIT)(func)
    return decorator
