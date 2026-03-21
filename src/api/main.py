"""FastAPI приложение Reflexio 24/7."""

from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _BaseModel
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
from src.api.routers import query
from src.api.routers import commitments
from src.api.routers import admin
from src.api.routers import mirror
from src.core.bootstrap import lifespan
from src.utils.config import settings
from src.utils.logging import get_logger, setup_logging
from src.utils.rate_limiter import RateLimitConfig, setup_rate_limiting

setup_logging()
logger = get_logger("api")

limiter = Limiter(key_func=get_remote_address)


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(
    title="Reflexio 24/7",
    description="Цифровая память всей жизни — evidence-based memory platform",
    version="0.5.2-beta",
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
app.include_router(graph.router)  # Sprint 2: Social Graph
app.include_router(compliance.router)  # Sprint 2: KZ GDPR Compliance
app.include_router(query.router)  # v1.0: Query Engine (5 unified tools)
app.include_router(commitments.router)  # v0.5: Commitment Extraction (Relationship Guardian)
app.include_router(admin.router)
app.include_router(mirror.router)  # Mirror portrait endpoint

from src.api.routers import profile  # noqa: E402

app.include_router(profile.router)  # User Profile (auto + manual knowledge)

# ── v1 compatibility layer ────────────────────
# ПОЧЕМУ alias-слой вместо немедленного hard cutover:
# существующие Android/ops клиенты уже завязаны на текущие пути.
# /v1 даёт формальный контракт для новых интеграций без поломки старых.
for _router in (
    ingest.router,
    asr.router,
    digest.router,
    metrics.router,
    search.router,
    voice.router,
    websocket.router,
    analyze.router,
    enrichment.router,
    memory.router,
    audit.router,
    balance.router,
    health_metrics.router,
    graph.router,
    compliance.router,
    query.router,
    commitments.router,
    admin.router,
    mirror.router,
):
    app.include_router(_router, prefix="/v1")


# ── Global Exception Handler ──────────────────
# ПОЧЕМУ: без этого необработанные исключения возвращают сырой traceback
# клиенту — утечка внутренних деталей (пути, версии библиотек, SQL).
# Handler ловит всё, логирует для отладки, клиенту — generic 500.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
@limiter.limit(RateLimitConfig.HEALTH_LIMIT)
async def health(request: Request, response: Response):
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.5.2-beta",
    }


@app.get("/v1/health", include_in_schema=False)
@limiter.limit(RateLimitConfig.HEALTH_LIMIT)
async def health_v1(request: Request, response: Response):
    """Версионированный health alias."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.5.2-beta",
    }


# ── v1.0: One Interface ────────────────────────────────────────────────────
# POST /ask — единственная точка входа для пользователя.
# Оркестратор сам выбирает тулы, параллельно вызывает, объединяет ответ.
# Пользователь не знает о тулах, роутерах, event_ids.


class AskRequest(_BaseModel):
    question: str
    include_evidence: bool = False


@app.post("/ask")
@limiter.limit("30/minute")
async def ask(request: Request, response: Response, body: AskRequest):
    """
    One Interface — задай вопрос, получи ответ с confidence.

    Оркестратор автоматически:
      1. Анализирует интент
      2. Выбирает нужные тулы (query_events / get_digest / get_person_insights)
      3. Вызывает параллельно (target: ≤400 ms)
      4. Объединяет confidence
      5. Возвращает минимальный ответ

    Response:
      answer          — текстовый ответ (минимальный)
      confidence      — 0.0–1.0
      confidence_label — high / medium / low / speculative
      data            — структурированные данные от каждого тула
      evidence_count  — кол-во источников
      needs_clarification — true если speculative
      total_ms        — latency
    """
    from src.core.orchestrator import orchestrate

    result = await orchestrate(body.question)

    response: dict = {
        "answer": result.answer,
        "confidence": result.confidence,
        "confidence_label": result.confidence_label,
        "evidence_count": result.evidence_count,
        "tools_used": result.tools_used,
        "total_ms": result.total_ms,
        "needs_clarification": result.needs_clarification,
        "data": result.data,
        "primary_tool": result.primary_tool,
    }
    if result.warning:
        response["warning"] = result.warning
    if body.include_evidence:
        response["tools_used"] = result.tools_used

    return response


@app.get("/")
async def root():
    """Корневой endpoint со списком всех доступных endpoints."""
    return {
        "service": "Reflexio 24/7",
        "version": "0.5.2-beta",
        "endpoints": {
            "health": "/health",
            "ingest_audio": "/ingest/audio",
            "transcribe": "/asr/transcribe",
            "status": "/ingest/status/{file_id}",
            "pipeline_status": "/ingest/pipeline-status",
            "incident_status": "/ingest/incident-status",
            "client_signpost": "POST /ingest/client-signpost",
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
