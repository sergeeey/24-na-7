"""FastAPI приложение Reflexio 24/7."""
import os
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger
from src.utils.rate_limiter import setup_rate_limiting, RateLimitConfig
from src.api.middleware.input_guard_middleware import input_guard_middleware
from src.api.middleware.safe_middleware import safe_middleware

# Импорт роутеров
from src.api.routers import ingest
from src.api.routers import asr
from src.api.routers import digest
from src.api.routers import metrics
from src.api.routers import search
from src.api.routers import voice
from src.api.routers import websocket
from src.api.routers import analyze

# Настройка логирования
setup_logging()
logger = get_logger("api")

# Rate Limiting
limiter = Limiter(key_func=get_remote_address)

# Создаём приложение
app = FastAPI(
    title="Reflexio 24/7",
    description="Умный диктофон и дневной анализатор",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Настраиваем Rate Limiting
limiter = setup_rate_limiting(app)

# Подключаем middleware
app.middleware("http")(input_guard_middleware)
app.middleware("http")(safe_middleware)

# Подключаем роутеры
app.include_router(ingest.router)
app.include_router(asr.router)
app.include_router(digest.router)
app.include_router(metrics.router)
app.include_router(search.router)
app.include_router(voice.router)
app.include_router(websocket.router)
app.include_router(analyze.router)


@app.on_event("startup")
async def startup():
    """Инициализация при старте."""
    logger.info("Reflexio API starting", host=settings.API_HOST, port=settings.API_PORT)
    
    # Проверяем SAFE checker
    from src.api.middleware.safe_middleware import get_safe_checker
    safe_checker = get_safe_checker()
    if safe_checker:
        logger.info("SAFE validation enabled", mode=os.getenv("SAFE_MODE", "audit"))
    
    # Запускаем health monitoring loop
    try:
        from src.monitor.health import periodic_check
        
        # Запускаем в фоне
        asyncio.create_task(periodic_check(interval=300))  # каждые 5 минут
        logger.info("health_monitor_started")
    except Exception as e:
        logger.warning("health_monitor_failed", error=str(e))


@app.get("/health")
@limiter.limit(RateLimitConfig.HEALTH_LIMIT)
async def health(request: Request, response: Response):
    """
    Health check endpoint.
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/health"
    ```
    
    **Пример ответа:**
    ```json
    {
        "status": "ok",
        "timestamp": "2024-02-17T12:00:00",
        "version": "0.1.0"
    }
    ```
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.1.0",
    }


@app.get("/")
async def root():
    """
    Корневой endpoint со списком всех доступных endpoints.
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/"
    ```
    
    **Пример ответа:**
    ```json
    {
        "service": "Reflexio 24/7",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "ingest_audio": "/ingest/audio",
            "transcribe": "/asr/transcribe",
            "status": "/ingest/status/{file_id}",
            "digest_today": "/digest/today",
            "digest_date": "/digest/{date}",
            "density_analysis": "/digest/{date}/density",
            "metrics": "/metrics",
            "search_phrases": "/search/phrases",
            "recognize_intent": "/voice/intent",
            "ws_ingest": "/ws/ingest"
        }
    }
    ```
    """
    return {
        "service": "Reflexio 24/7",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "ingest_audio": "/ingest/audio",
            "transcribe": "/asr/transcribe",
            "status": "/ingest/status/{file_id}",
            "digest_today": "/digest/today",
            "digest_date": "/digest/{date}",
            "density_analysis": "/digest/{date}/density",
            "metrics": "/metrics",
            "search_phrases": "/search/phrases",
            "recognize_intent": "/voice/intent",
            "ws_ingest": "/ws/ingest",
        },
    }
