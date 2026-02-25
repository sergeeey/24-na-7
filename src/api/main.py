"""FastAPI приложение Reflexio 24/7."""
import asyncio
import os
from datetime import datetime

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.middleware.auth_middleware import auth_middleware
from src.api.middleware.input_guard_middleware import input_guard_middleware
from src.api.middleware.safe_middleware import safe_middleware
from src.api.routers import analyze
from src.api.routers import asr
from src.api.routers import balance
from src.api.routers import health_metrics
from src.api.routers import audit
from src.api.routers import digest
from src.api.routers import enrichment
from src.api.routers import ingest
from src.api.routers import memory
from src.api.routers import metrics
from src.api.routers import search
from src.api.routers import voice
from src.api.routers import websocket
from src.memory.semantic_memory import ensure_semantic_memory_tables
from src.storage.integrity import ensure_integrity_tables
from src.storage.ingest_persist import ensure_ingest_tables
from src.balance.storage import ensure_balance_tables
from src.storage.health_metrics import ensure_health_tables
from src.persongraph.service import ensure_person_graph_tables
from src.utils.config import settings
from src.utils.logging import get_logger, setup_logging
from src.utils.rate_limiter import RateLimitConfig, setup_rate_limiting

setup_logging()
logger = get_logger("api")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Reflexio 24/7",
    description="Умный диктофон и дневной анализатор",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

limiter = setup_rate_limiting(app)

# CORS — только явно разрешённые origins.
# ПОЧЕМУ: без CORS браузер блокирует запросы с других доменов.
# В продакшене: заменить на реальный домен (CORS_ORIGINS=https://app.example.com).
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# Порядок обработки запроса: CORS → auth → input_guard → safe → handler
app.middleware("http")(input_guard_middleware)
app.middleware("http")(safe_middleware)
app.middleware("http")(auth_middleware)

app.include_router(ingest.router)
app.include_router(asr.router)
app.include_router(digest.router)
app.include_router(metrics.router)
app.include_router(search.router)
app.include_router(voice.router)
app.include_router(websocket.router)
app.include_router(analyze.router)
app.include_router(enrichment.router)
app.include_router(memory.router)
app.include_router(audit.router)
app.include_router(balance.router)
app.include_router(health_metrics.router)


@app.on_event("startup")
async def startup():
    """Инициализация при старте."""
    logger.info("Reflexio API starting", host=settings.API_HOST, port=settings.API_PORT)

    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_ingest_tables(db_path)
    ensure_integrity_tables(db_path)
    ensure_semantic_memory_tables(db_path)
    ensure_balance_tables(db_path)
    ensure_health_tables(db_path)
    ensure_person_graph_tables(db_path)

    from src.api.middleware.safe_middleware import get_safe_checker

    safe_checker = get_safe_checker()
    if safe_checker:
        logger.info("SAFE validation enabled", mode=os.getenv("SAFE_MODE", "audit"))

    try:
        from src.monitor.health import periodic_check

        asyncio.create_task(periodic_check(interval=300))
        logger.info("health_monitor_started")
    except Exception as e:
        logger.warning("health_monitor_failed", error=str(e))


@app.get("/health")
@limiter.limit(RateLimitConfig.HEALTH_LIMIT)
async def health(request: Request, response: Response):
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.1.0",
    }


@app.get("/")
async def root():
    """Корневой endpoint со списком всех доступных endpoints."""
    return {
        "service": "Reflexio 24/7",
        "version": "0.1.0",
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
            "enrichment": "/enrichment/by-ingest/{file_id}",
            "memory_retrieve": "/memory/retrieve?q=...",
            "audit_ingest": "/audit/ingest/{ingest_id}",
            "balance_wheel": "/balance/wheel?date=YYYY-MM-DD",
            "balance_domains": "/balance/domains",
            "health_metrics": "/health/metrics",
        },
        "feature_flags": {
            "privacy_mode": settings.PRIVACY_MODE,
            "memory_enabled": settings.MEMORY_ENABLED,
            "retrieval_enabled": settings.RETRIEVAL_ENABLED,
            "integrity_chain_enabled": settings.INTEGRITY_CHAIN_ENABLED,
        },
    }




