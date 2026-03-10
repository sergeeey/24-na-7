"""FastAPI приложение Reflexio 24/7."""

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
from src.storage.db import ReflexioDB, ensure_all_tables, get_reflexio_db, run_migrations
from src.utils.config import settings
from src.utils.logging import get_logger, setup_logging
from src.utils.rate_limiter import RateLimitConfig, setup_rate_limiting

setup_logging()
logger = get_logger("api")

limiter = Limiter(key_func=get_remote_address)


# Блокировка по дате для precompute дайджеста (избегаем двух одновременных за одну дату)
_digest_precompute_locks: dict[str, threading.Lock] = {}
_digest_precompute_dict_lock = threading.Lock()


# ──────────────────────────────────────────────
# APScheduler — ежедневный compliance cleanup
# ──────────────────────────────────────────────


def _run_ingest_watchdog() -> None:
    """Помечает зависшие ingest_queue записи (pending > 30 мин) как retryable_error.

    ПОЧЕМУ: Закон исключённого третьего — запись либо обработана, либо нет.
    Без watchdog запись может навсегда застрять в 'pending' если worker упал
    посередине (OOM, перезапуск контейнера). 30 мин — с запасом: ASR + enrichment
    занимают 10-60 секунд. Если за 30 мин не обработано — точно зависло.
    """
    try:
        from src.storage.db import get_reflexio_db

        db_path = settings.STORAGE_PATH / "reflexio.db"
        db = get_reflexio_db(db_path)
        cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
        with db.transaction():
            result = db.execute(
                """
                UPDATE ingest_queue
                SET status='retryable_error',
                    processing_status='received',
                    error_code='watchdog_stuck_pending',
                    error_message='watchdog: stuck in pending > 30min',
                    processed_at=?
                WHERE status='pending' AND created_at < ?
                """,
                (datetime.now().isoformat(), cutoff),
            )
        affected = result.rowcount if hasattr(result, "rowcount") else 0
        if affected:
            logger.warning("ingest_watchdog_reaped", stuck_records=affected)
    except Exception as e:
        logger.error("ingest_watchdog_failed", error=str(e))


def _run_audio_retention_cleanup() -> None:
    """Удаляет WAV файлы старше AUDIO_RETENTION_HOURS."""
    import time

    uploads_dir = Path("src/storage/uploads")
    if not uploads_dir.exists():
        return
    cutoff = time.time() - settings.AUDIO_RETENTION_HOURS * 3600
    removed = 0
    for f in uploads_dir.glob("*.wav"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed += 1
    if removed:
        logger.info(
            "audio_retention_cleanup",
            removed=removed,
            retention_hours=settings.AUDIO_RETENTION_HOURS,
        )


def _run_episode_lifecycle() -> None:
    """Закрывает неактивные эпизоды и переводит завершённые в summarized."""
    try:
        from src.memory.episodes import close_stale_episodes, finalize_closed_episodes

        db_path = settings.STORAGE_PATH / "reflexio.db"
        closed = close_stale_episodes(db_path)
        summarized = finalize_closed_episodes(db_path)
        if closed or summarized:
            logger.info(
                "episode_lifecycle_tick",
                closed=closed,
                summarized=summarized,
            )
    except Exception as e:
        logger.error("episode_lifecycle_failed", error=str(e))


def _run_daily_digest_precompute() -> None:
    """
    Pre-compute дневного дайджеста в фоне.

    ПОЧЕМУ pre-compute: endpoint /digest/daily делал 3-5 LLM вызовов
    (Chain of Density + extract_tasks + analyze_emotions) = 4+ минут.
    Любой HTTP timeout < 4 мин → ошибка на клиенте.
    Решение: генерируем заранее, клиент получает кеш мгновенно.

    Запускается APScheduler в 18:00 (Алматы). Если сервер был выключен —
    misfire_grace_time=7200 даёт 2 часа на catch-up.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    with _digest_precompute_dict_lock:
        date_lock = _digest_precompute_locks.setdefault(today, threading.Lock())
    if not date_lock.acquire(blocking=False):
        logger.info("digest_precompute_skipped_already_running", date=today)
        return
    try:
        _run_digest_precompute_body(today)
    finally:
        date_lock.release()


def _run_digest_precompute_body(today: str) -> None:
    """Внутренняя реализация precompute под блокировкой по дате."""
    import json as _json

    db: Any = None
    try:
        from src.digest.generator import DigestGenerator
        from src.storage.db import get_reflexio_db

        db_path = settings.STORAGE_PATH / "reflexio.db"
        db = get_reflexio_db(db_path)

        # Помечаем статус "generating"
        db.execute(
            "INSERT OR REPLACE INTO digest_cache (date, digest_json, generated_at, status) VALUES (?, ?, ?, ?)",
            (today, "{}", datetime.now().isoformat(), "generating"),
        )
        db.conn.commit()

        logger.info("digest_precompute_started", date=today)

        generator = DigestGenerator(db_path=db_path)
        result = generator.get_daily_digest_json(datetime.strptime(today, "%Y-%m-%d").date())

        db.execute(
            "INSERT OR REPLACE INTO digest_cache (date, digest_json, generated_at, status) VALUES (?, ?, ?, ?)",
            (today, _json.dumps(result, ensure_ascii=False), datetime.now().isoformat(), "ready"),
        )
        db.conn.commit()
        logger.info(
            "digest_precompute_done", date=today, recordings=result.get("total_recordings", 0)
        )

        # Event log: фиксируем завершение дайджеста как lifecycle-событие дня
        try:
            from src.storage.event_log import log_event, STAGE_DIGEST_COMPUTED

            log_event(
                today,
                STAGE_DIGEST_COMPUTED,
                details={
                    "recordings": result.get("total_recordings", 0),
                    "sources": result.get("sources_count", 0),
                },
            )
        except Exception:
            pass

    except Exception as e:
        logger.error("digest_precompute_failed", error=str(e))
        try:
            if db is not None:
                db.execute(
                    "UPDATE digest_cache SET status = 'failed' WHERE date = ?",
                    (today,),
                )
                db.conn.commit()
        except Exception:
            pass


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
# Orphan WAV sweep — zero-retention compliance
# ──────────────────────────────────────────────


async def _orphan_sweep(storage_path: Path, interval: int = 300, max_age_hours: int = 1) -> None:
    """
    Фоновая задача: удаляет WAV-сироты старше max_age_hours.

    Сканирует uploads/ и recordings/ каждые `interval` секунд.
    Использует secure_delete для compliance с KZ GDPR.
    """
    from src.utils.secure_delete import secure_delete

    scan_dirs = [
        storage_path / "uploads",
        storage_path / "recordings",
    ]
    cutoff_delta = timedelta(hours=max_age_hours)

    while True:
        await asyncio.sleep(interval)
        try:
            deleted = 0
            cutoff = datetime.now(tz=timezone.utc) - cutoff_delta
            for scan_dir in scan_dirs:
                if not scan_dir.exists():
                    continue
                for wav_file in scan_dir.glob("*.wav"):
                    try:
                        mtime = datetime.fromtimestamp(wav_file.stat().st_mtime, tz=timezone.utc)
                        if mtime < cutoff:
                            secure_delete(wav_file)
                            deleted += 1
                    except Exception as e:
                        logger.warning("orphan_sweep_file_error", file=str(wav_file), error=str(e))
            if deleted > 0:
                logger.info("orphan_sweep_done", deleted=deleted)
        except Exception as e:
            logger.error("orphan_sweep_failed", error=str(e))


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
    ensure_all_tables(db_path)
    applied = run_migrations(db_path)
    if applied:
        logger.info("migrations_applied", count=len(applied), names=applied)

    # ПОЧЕМУ верификация WAL: get_connection() ставит WAL при создании,
    # но это может не сработать (read-only FS, permissions). Проверяем факт.
    try:
        db = get_reflexio_db(db_path)
        _wal_mode = db.fetchone("PRAGMA journal_mode")[0]
        if _wal_mode == "wal":
            logger.info("wal_mode_verified", db_path=str(db_path))
        else:
            logger.warning("wal_mode_not_active", actual=_wal_mode, db_path=str(db_path))
    except Exception as e:
        logger.error("wal_verification_failed", error=str(e))

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

    # ПОЧЕМУ orphan sweep: ingest сохраняет WAV в uploads/ и может крашнуться
    # до удаления. Фоновая задача — defense in depth для zero-retention.
    asyncio.create_task(_orphan_sweep(settings.STORAGE_PATH, interval=300))

    # Enrichment workers: async queue для LLM-обогащения
    from src.enrichment.worker import get_enrichment_worker

    enrichment_worker = get_enrichment_worker()
    await enrichment_worker.start()

    # Ingest workers: принятый по WebSocket аудио обрабатывается в фоне (ASR + enrichment).
    from src.api.routers.websocket import get_ingest_result_registry
    from src.ingest.worker import get_ingest_worker

    ingest_worker = get_ingest_worker(get_ingest_result_registry())
    await ingest_worker.start()

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
        # ПОЧЕМУ 12:00 UTC: пользователь в Алматы (UTC+6).
        # 12:00 UTC = 18:00 Алматы. Генерация 2-5 мин → готово к 18:05 Алматы.
        scheduler.add_job(
            _run_daily_digest_precompute,
            trigger="cron",
            hour=12,
            minute=0,
            id="digest_precompute",
            replace_existing=True,
            misfire_grace_time=7200,
        )
        # Ingest watchdog — помечает зависшие pending записи как error
        scheduler.add_job(
            _run_ingest_watchdog,
            trigger="interval",
            minutes=15,
            id="ingest_watchdog",
            replace_existing=True,
        )
        scheduler.add_job(
            _run_episode_lifecycle,
            trigger="interval",
            minutes=5,
            id="episode_lifecycle",
            replace_existing=True,
        )
        # Audio retention cleanup — удаляет WAV старше AUDIO_RETENTION_HOURS
        if settings.AUDIO_RETENTION_HOURS > 0:
            scheduler.add_job(
                _run_audio_retention_cleanup,
                trigger="interval",
                hours=6,
                id="audio_retention_cleanup",
                replace_existing=True,
            )
        scheduler.start()
        logger.info(
            "apscheduler_started",
            jobs="compliance_cleanup@03:00, digest_precompute@12:00UTC(18:00ALM), episode_lifecycle@5m",
        )
    except ImportError:
        logger.warning("apscheduler_not_installed", hint="pip install apscheduler")
    except Exception as e:
        logger.error("apscheduler_failed", error=str(e))

    yield  # ── Приложение работает ──────────────

    # ── Shutdown ─────────────────────────────────
    await ingest_worker.stop()
    await enrichment_worker.stop()
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("apscheduler_stopped")
    ReflexioDB.close_all_instances()
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
app.include_router(graph.router)  # Sprint 2: Social Graph
app.include_router(compliance.router)  # Sprint 2: KZ GDPR Compliance
app.include_router(query.router)  # v1.0: Query Engine (5 unified tools)
app.include_router(commitments.router)  # v0.5: Commitment Extraction (Relationship Guardian)
app.include_router(admin.router)


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
        "version": "0.2.0",
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
        "version": "0.2.0",
        "endpoints": {
            "health": "/health",
            "ingest_audio": "/ingest/audio",
            "transcribe": "/asr/transcribe",
            "status": "/ingest/status/{file_id}",
            "pipeline_status": "/ingest/pipeline-status",
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
