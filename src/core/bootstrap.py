"""Bootstrap и lifecycle для FastAPI-приложения Reflexio 24/7."""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI

from src.storage.db import ReflexioDB, ensure_all_tables, get_reflexio_db, run_migrations
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api")

_digest_precompute_locks: dict[str, threading.Lock] = {}
_digest_precompute_dict_lock = threading.Lock()


def _run_ingest_watchdog() -> None:
    """Помечает зависшие ingest_queue записи (pending > 30 мин) как retryable_error."""
    try:
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
    except Exception as e:  # pragma: no cover
        logger.error("ingest_watchdog_failed", error=str(e))


def _run_audio_retention_cleanup() -> None:
    """Удаляет WAV файлы старше AUDIO_RETENTION_HOURS."""
    import time

    uploads_dir = Path("src/storage/uploads")
    if not uploads_dir.exists():
        return
    cutoff = time.time() - settings.AUDIO_RETENTION_HOURS * 3600
    removed = 0
    for wav_file in uploads_dir.glob("*.wav"):
        if wav_file.stat().st_mtime < cutoff:
            wav_file.unlink(missing_ok=True)
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
            logger.info("episode_lifecycle_tick", closed=closed, summarized=summarized)
    except Exception as e:  # pragma: no cover
        logger.error("episode_lifecycle_failed", error=str(e))


def _run_digest_precompute_body(today: str) -> None:
    """Внутренняя реализация precompute под блокировкой по дате."""
    import json as _json

    db: Any = None
    try:
        from src.digest.generator import DigestGenerator
        from src.storage.event_log import STAGE_DIGEST_COMPUTED, log_event

        db_path = settings.STORAGE_PATH / "reflexio.db"
        db = get_reflexio_db(db_path)
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
        logger.info("digest_precompute_done", date=today, recordings=result.get("total_recordings", 0))

        try:
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
                db.execute("UPDATE digest_cache SET status = 'failed' WHERE date = ?", (today,))
                db.conn.commit()
        except Exception:
            pass


def _run_daily_digest_precompute() -> None:
    """Pre-compute дневного дайджеста в фоне."""
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


def _run_compliance_cleanup() -> None:
    """TTL-очистка биометрических данных окружения."""
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
    except Exception as e:  # pragma: no cover
        logger.error("scheduled_compliance_failed", error=str(e))


async def _orphan_sweep(storage_path: Path, interval: int = 300, max_age_hours: int = 1) -> None:
    """Фоновая задача: удаляет WAV-сироты старше max_age_hours."""
    from src.utils.secure_delete import secure_delete

    scan_dirs = [storage_path / "uploads", storage_path / "recordings"]
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
        except Exception as e:  # pragma: no cover
            logger.error("orphan_sweep_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """Lifecycle: startup -> yield -> shutdown."""
    logger.info("Reflexio API starting", host=settings.API_HOST, port=settings.API_PORT)

    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_all_tables(db_path)
    applied = run_migrations(db_path)
    if applied:
        logger.info("migrations_applied", count=len(applied), names=applied)

    try:
        db = get_reflexio_db(db_path)
        wal_mode = db.fetchone("PRAGMA journal_mode")[0]
        if wal_mode == "wal":
            logger.info("wal_mode_verified", db_path=str(db_path))
        else:
            logger.warning("wal_mode_not_active", actual=wal_mode, db_path=str(db_path))
    except Exception as e:
        logger.error("wal_verification_failed", error=str(e))

    from src.api.middleware.safe_middleware import get_safe_checker

    safe_checker = get_safe_checker()
    if safe_checker:
        logger.info("SAFE validation enabled", mode=os.getenv("SAFE_MODE", "audit"))

    try:
        from src.monitor.health import periodic_check

        asyncio.create_task(periodic_check(interval=300))
        logger.info("health_monitor_started")
    except Exception as e:  # pragma: no cover
        logger.warning("health_monitor_failed", error=str(e))

    asyncio.create_task(_orphan_sweep(settings.STORAGE_PATH, interval=300))

    from src.enrichment.worker import get_enrichment_worker

    enrichment_worker = get_enrichment_worker()
    await enrichment_worker.start()

    from src.api.routers.websocket import get_ingest_result_registry
    from src.ingest.worker import get_ingest_worker

    ingest_worker = get_ingest_worker(get_ingest_result_registry())
    await ingest_worker.start()

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
            misfire_grace_time=3600,
        )
        scheduler.add_job(
            _run_daily_digest_precompute,
            trigger="cron",
            hour=12,
            minute=0,
            id="digest_precompute",
            replace_existing=True,
            misfire_grace_time=7200,
        )
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
    except Exception as e:  # pragma: no cover
        logger.error("apscheduler_failed", error=str(e))

    yield

    await ingest_worker.stop()
    await enrichment_worker.stop()
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("apscheduler_stopped")
    ReflexioDB.close_all_instances()
    logger.info("Reflexio API stopped")
