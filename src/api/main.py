"""FastAPI приложение Reflexio 24/7."""
import asyncio
import os
from contextlib import asynccontextmanager
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
from src.api.routers import compliance
from src.api.routers import graph
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


# ──────────────────────────────────────────────
# APScheduler — ежедневный compliance cleanup
# ──────────────────────────────────────────────

def _run_compliance_cleanup() -> None:
    """
    TTL-очистка биометрических данных окружения.

    ПОЧЕМУ sync, не async: APScheduler BackgroundScheduler работает в
    отдельном потоке. Sync-функция безопаснее чем запускать coroutine
    из фонового потока через asyncio.run_coroutine_threadsafe.
    """
    try:
        from src.persongraph.compliance import BiometricComplianceManager
        db_path = settings.STORAGE_PATH / "reflexio.db"
        mgr = BiometricComplianceManager(db_path)
        report = mgr.run_cleanup()
        logger.info(
            "scheduled_compliance_done",
            deleted_unidentified=report.deleted_unidentified,
            deleted_pending=report.deleted_pending_expired,
            profiles_expired=len(report.profiles_expired),
        )
    except Exception as e:
        logger.error("scheduled_compliance_failed", error=str(e))


# ──────────────────────────────────────────────
# FastAPI lifespan (startup + shutdown)
# ПОЧЕМУ @asynccontextmanager вместо @app.on_event:
#   on_event устарел в FastAPI 0.93+. lifespan — официальный способ.
#   Позволяет корректно остановить APScheduler при shutdown.
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    """Lifecycle: startup → yield → shutdown."""
    # ── Startup ──────────────────────────────────
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

    # Health monitor
    try:
        from src.monitor.health import periodic_check
        asyncio.create_task(periodic_check(interval=300))
        logger.info("health_monitor_started")
    except Exception as e:
        logger.warning("health_monitor_failed", error=str(e))

    # APScheduler: ежедневный compliance cleanup в 03:00
    scheduler = None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _run_compliance_cleanup,
            trigger="cron",
            hour=3,
            minute=0,
            id="compliance_cleanup",
            replace_existing=True,
            misfire_grace_time=3600,  # 1 час — если сервер был выключен
        )
        scheduler.start()
        logger.info("apscheduler_started", job="compliance_cleanup@03:00")
    except ImportError:
        logger.warning("apscheduler_not_installed", hint="pip install apscheduler")
    except Exception as e:
        logger.error("apscheduler_failed", error=str(e))

    yield  # ── Приложение работает ──────────────

    # ── Shutdown ─────────────────────────────────
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("apscheduler_stopped")
    logger.info("Reflexio API stopped")


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(
    title="Reflexio 24/7",
    description="Умный диктофон и дневной анализатор",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

limiter = setup_rate_limiting(app)

# CORS — только явно разрешённые origins.
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Порядок обработки: CORS → auth → input_guard → safe → handler
app.middleware("http")(input_guard_middleware)
app.middleware("http")(safe_middleware)
app.middleware("http")(auth_middleware)

# ── Роутеры ───────────────────────────────────
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
app.include_router(graph.router)       # Sprint 2: Social Graph
app.include_router(compliance.router)  # Sprint 2: KZ GDPR Compliance


@app.get("/health")
@limiter.limit(RateLimitConfig.HEALTH_LIMIT)
async def health(request: Request, response: Response):
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.2.0",
    }


@app.get("/")
async def root():
    """Корневой endpoint со списком всех доступных endpoints."""
    return {
        "service": "Reflexio 24/7",
        "version": "0.2.0",
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
            # Social Graph (Sprint 2)
            "graph_persons": "/graph/persons",
            "graph_pending": "/graph/pending",
            "graph_approve": "POST /graph/approve/{name}",
            "graph_reject": "POST /graph/reject/{name}",
            "graph_stats": "/graph/stats",
            # Compliance (Sprint 2)
            "compliance_status": "/compliance/status",
            "compliance_erase": "DELETE /compliance/erase/{person}",
            "compliance_cleanup": "POST /compliance/run-cleanup",
        },
        "feature_flags": {
            "privacy_mode": settings.PRIVACY_MODE,
            "memory_enabled": settings.MEMORY_ENABLED,
            "retrieval_enabled": settings.RETRIEVAL_ENABLED,
            "integrity_chain_enabled": settings.INTEGRITY_CHAIN_ENABLED,
        },
    }
