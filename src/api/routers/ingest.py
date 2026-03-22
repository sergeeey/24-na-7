"""Роутер для загрузки и обработки аудио."""

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.middleware.safe_middleware import get_safe_checker
from src.core.audio_processing import process_audio_bytes, validate_safe_file_size
from src.ingest.worker import IngestTask, get_ingest_worker
from src.storage.ingest_persist import ensure_ingest_tables
from src.utils.incidents import (
    build_incident_summary,
    load_incident_ledger,
    validate_incident_ledger,
)
from src.utils.config import settings  # noqa: F401
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitConfig

logger = get_logger("api.ingest")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/ingest", tags=["ingest"])
_REPROCESS_STALE_MINUTES = 30


class ClientSignpostRequest(BaseModel):
    source: str
    route_kind: str
    primary_url: str
    resolved_url: str
    decision: str
    is_local_primary: bool = False
    debug_build: bool = False


def _round_maybe(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _build_llm_circuit_breaker_state() -> dict[str, object]:
    from src.llm.providers import get_llm_circuit_breaker_stats

    providers = get_llm_circuit_breaker_stats()
    open_providers = sorted(
        provider_name
        for provider_name, provider_stats in providers.items()
        if provider_stats.get("state") == "open"
    )
    half_open_providers = sorted(
        provider_name
        for provider_name, provider_stats in providers.items()
        if provider_stats.get("state") == "half_open"
    )
    overall_state = "closed"
    if open_providers:
        overall_state = "open"
    elif half_open_providers:
        overall_state = "half_open"
    return {
        "state": overall_state,
        "open_providers": open_providers,
        "half_open_providers": half_open_providers,
        "providers": providers,
    }


def _runtime_storage_is_golden_path() -> bool:
    # WHY: check that storage path exists and DB file is present,
    # not a fixed convention ("runtime/storage") that fails in Docker.
    p = Path(settings.STORAGE_PATH)
    return p.exists() and (p / "reflexio.db").exists()


def _build_golden_path_contract(
    *,
    server_ok: bool,
    transcriptions_total: int,
    ingest_health: dict[str, object],
    incident_status: dict[str, object],
) -> dict[str, object]:
    signal_by_signature = {
        item.get("signature"): item.get("signal", {})
        for item in incident_status.get("incidents", [])
        if isinstance(item, dict)
    }
    stale_counts = ingest_health.get("stale_counts", {})
    micro_signal = signal_by_signature.get("micro_wav_segments_under_min_size", {})
    unsupported_signal = signal_by_signature.get(
        "unsupported_language_unknown_filters_valid_ru_audio",
        {},
    )
    routing_signal = signal_by_signature.get(
        "android_debug_falls_back_to_remote_when_local_alive",
        {},
    )
    checks = {
        "server_ok": bool(server_ok),
        "runtime_storage": _runtime_storage_is_golden_path(),
        "transcription_available": transcriptions_total > 0,
        "stale_received_ok": int(stale_counts.get("received", 0) or 0) == 0,
        "stale_asr_pending_ok": int(stale_counts.get("asr_pending", 0) or 0) == 0,
        "micro_wav_ok": micro_signal.get("state") != "alert",
        "unsupported_language_ok": unsupported_signal.get("state") != "alert",
        "android_route_signpost_observed": routing_signal.get("state") != "unknown",
    }
    blocking_checks = (
        "server_ok",
        "runtime_storage",
        "transcription_available",
        "stale_received_ok",
        "stale_asr_pending_ok",
        "micro_wav_ok",
        "unsupported_language_ok",
    )
    return {
        "storage_path": str(settings.STORAGE_PATH),
        "checks": checks,
        "non_blocking_checks": ["android_route_signpost_observed"],
        "ready": all(bool(checks[name]) for name in blocking_checks),
    }


def _is_stale_for_reprocess(created_at: str | None) -> bool:
    if not created_at:
        return False
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return False
    return created <= datetime.now() - timedelta(minutes=_REPROCESS_STALE_MINUTES)


def _build_slo_state(
    *,
    ingest_queue: dict[str, int],
    episode_counts: dict[str, int],
    day_thread_counts: dict[str, int],
    quality_counts: dict[str, int],
    memory_health: dict[str, float | int | bool],
    ingest_health: dict[str, object] | None = None,
) -> dict[str, object]:
    alerts: list[str] = []
    trusted_fraction = float(memory_health.get("trusted_fraction", 0.0) or 0.0)
    review_fraction = float(memory_health.get("review_fraction", 0.0) or 0.0)
    thread_coverage = float(memory_health.get("thread_coverage", 0.0) or 0.0)
    digest_incomplete = int(memory_health.get("digest_incomplete_context_total", 0) or 0)
    ingest_health = ingest_health or {}
    stale_counts = ingest_health.get("stale_counts", {}) if isinstance(ingest_health, dict) else {}
    if isinstance(stale_counts, dict):
        stale_received = int(stale_counts.get("received", 0) or 0)
        stale_asr_pending = int(stale_counts.get("asr_pending", 0) or 0)
    else:
        stale_received = 0
        stale_asr_pending = 0

    if trusted_fraction < 0.5:
        alerts.append("low_trusted_fraction")
    if review_fraction > 0.5:
        alerts.append("high_review_fraction")
    if int(quality_counts.get("quarantined", 0)) > 0:
        alerts.append("episodes_quarantined_present")
    if int(ingest_queue.get("quarantine", 0)) > 0:
        alerts.append("ingest_quarantine_present")
    if int(episode_counts.get("summarized", 0)) > 0 and thread_coverage < 0.5:
        alerts.append("low_day_thread_coverage")
    if digest_incomplete > 0:
        alerts.append("degraded_digest_present")
    if stale_received > 0:
        alerts.append("stale_received_present")
    if stale_asr_pending > 0:
        alerts.append("stale_asr_pending_present")

    status = "healthy"
    if alerts:
        status = "degraded"
    if any(
        code in alerts
        for code in (
            "episodes_quarantined_present",
            "ingest_quarantine_present",
        )
    ):
        status = "attention"

    return {
        "status": status,
        "alerts": alerts,
        "beta_thresholds": {
            "min_trusted_fraction": 0.5,
            "max_review_fraction": 0.5,
            "min_thread_coverage": 0.5,
            "max_digest_incomplete_context_total": 0,
        },
        "snapshot": {
            "trusted_fraction": trusted_fraction,
            "review_fraction": review_fraction,
            "thread_coverage": thread_coverage,
            "digest_incomplete_context_total": digest_incomplete,
            "episodes_summarized": int(episode_counts.get("summarized", 0)),
            "day_threads_trusted": int(day_thread_counts.get("trusted", 0)),
            "stale_received": stale_received,
            "stale_asr_pending": stale_asr_pending,
        },
    }


def _build_recent_day_trends(db, *, days_back: int) -> list[dict[str, object]]:
    anchor_candidates: list[date] = []
    for query in (
        "SELECT MAX(day_key) FROM episodes",
        "SELECT MAX(day_key) FROM day_threads",
        "SELECT MAX(date) FROM digest_cache",
        "SELECT MAX(date(created_at)) FROM ingest_queue",
        "SELECT MAX(date(created_at)) FROM structured_events WHERE is_current = 1",
    ):
        row = db.fetchone(query)
        value = row[0] if row and row[0] else None
        if not value:
            continue
        try:
            anchor_candidates.append(date.fromisoformat(str(value)))
        except ValueError:
            continue
    today = max(anchor_candidates) if anchor_candidates else date.today()
    digest_rows = {
        row["date"]: row["digest_json"]
        for row in db.fetchall(
            """
            SELECT date, digest_json
            FROM digest_cache
            WHERE date BETWEEN ? AND ?
            """,
            (
                (today - timedelta(days=days_back - 1)).isoformat(),
                today.isoformat(),
            ),
        )
    }

    recent_days: list[dict[str, object]] = []
    for offset in range(days_back):
        day_key = (today - timedelta(days=offset)).isoformat()
        trusted_count = db.fetchone(
            "SELECT COUNT(*) FROM episodes WHERE day_key = ? AND quality_state = 'trusted'",
            (day_key,),
        )[0]
        uncertain_count = db.fetchone(
            "SELECT COUNT(*) FROM episodes WHERE day_key = ? AND quality_state = 'uncertain'",
            (day_key,),
        )[0]
        garbage_count = db.fetchone(
            "SELECT COUNT(*) FROM episodes WHERE day_key = ? AND quality_state = 'garbage'",
            (day_key,),
        )[0]
        quarantined_count = db.fetchone(
            "SELECT COUNT(*) FROM episodes WHERE day_key = ? AND quality_state = 'quarantined'",
            (day_key,),
        )[0]
        day_thread_count = db.fetchone(
            "SELECT COUNT(*) FROM day_threads WHERE day_key = ?",
            (day_key,),
        )[0]
        long_thread_count = db.fetchone(
            """
            SELECT COUNT(DISTINCT long_thread_key)
            FROM day_threads
            WHERE day_key = ? AND long_thread_key IS NOT NULL AND long_thread_key != ''
            """,
            (day_key,),
        )[0]
        received_count = db.fetchone(
            "SELECT COUNT(*) FROM ingest_queue WHERE date(created_at) = ? AND status = 'received'",
            (day_key,),
        )[0]
        asr_pending_count = db.fetchone(
            "SELECT COUNT(*) FROM ingest_queue WHERE date(created_at) = ? AND status = 'asr_pending'",
            (day_key,),
        )[0]
        event_ready_count = db.fetchone(
            "SELECT COUNT(*) FROM ingest_queue WHERE date(created_at) = ? AND status = 'event_ready'",
            (day_key,),
        )[0]
        retryable_error_count = db.fetchone(
            "SELECT COUNT(*) FROM ingest_queue WHERE date(created_at) = ? AND status = 'retryable_error'",
            (day_key,),
        )[0]
        quarantined_ingest_count = db.fetchone(
            "SELECT COUNT(*) FROM ingest_queue WHERE date(created_at) = ? AND status = 'quarantined'",
            (day_key,),
        )[0]
        avg_received_to_processed_ms = db.fetchone(
            """
            SELECT AVG((julianday(processed_at) - julianday(created_at)) * 86400000.0)
            FROM ingest_queue
            WHERE date(created_at) = ?
              AND processed_at IS NOT NULL
              AND status IN ('transcribed', 'event_ready', 'retryable_error', 'quarantined', 'filtered')
            """,
            (day_key,),
        )[0]
        enrichment_latencies = [
            float(row[0])
            for row in db.fetchall(
                """
                SELECT enrichment_latency_ms
                FROM structured_events
                WHERE date(created_at) = ?
                  AND is_current = 1
                  AND enrichment_latency_ms IS NOT NULL
                  AND enrichment_latency_ms > 0
                """,
                (day_key,),
            )
            if row[0] is not None
        ]
        digest_payload = {}
        if day_key in digest_rows:
            try:
                digest_payload = json.loads(digest_rows[day_key] or "{}")
            except Exception:
                digest_payload = {}
        recent_days.append(
            {
                "day": day_key,
                "trusted_count": trusted_count,
                "uncertain_count": uncertain_count,
                "garbage_count": garbage_count,
                "quarantined_count": quarantined_count,
                "review_count": uncertain_count + garbage_count + quarantined_count,
                "day_thread_count": day_thread_count,
                "long_thread_count": long_thread_count,
                "received_count": received_count,
                "asr_pending_count": asr_pending_count,
                "event_ready_count": event_ready_count,
                "retryable_error_count": retryable_error_count,
                "quarantined_ingest_count": quarantined_ingest_count,
                "avg_received_to_processed_ms": _round_maybe(avg_received_to_processed_ms),
                "enrichment_latency_ms": {
                    "p50": _round_maybe(_percentile(enrichment_latencies, 0.50), 2),
                    "p95": _round_maybe(_percentile(enrichment_latencies, 0.95), 2),
                },
                "degraded_digest": bool(
                    digest_payload.get("degraded") or digest_payload.get("incomplete_context")
                ),
            }
        )
    return recent_days


def _build_incident_signal_state(
    *,
    state: str,
    value: int | None,
    source: str,
    details: str,
) -> dict[str, object]:
    return {
        "state": state,
        "value": value,
        "source": source,
        "details": details,
    }


def _build_incident_status_report(db, *, start_iso: str, end_iso: str) -> dict[str, object]:
    payload = load_incident_ledger()
    validation_errors = validate_incident_ledger(payload)
    incidents = payload.get("incidents", [])

    stale_received = db.fetchone(
        """
        SELECT COUNT(*) FROM ingest_queue
        WHERE status = 'received'
          AND created_at < datetime('now', '-30 minutes')
        """
    )[0]
    missing_enrichment = db.fetchone(
        """
        SELECT COUNT(*)
        FROM ingest_queue iq
        LEFT JOIN structured_events se
          ON se.is_current = 1
         AND se.transcription_id IN (
             SELECT id FROM transcriptions WHERE ingest_id = iq.id
         )
        WHERE iq.status = 'event_ready'
          AND iq.created_at BETWEEN ? AND ?
          AND se.id IS NULL
        """,
        (start_iso, end_iso),
    )[0]
    micro_segments = db.fetchone(
        """
        SELECT COUNT(*) FROM ingest_queue
        WHERE created_at BETWEEN ? AND ?
          AND file_size <= 512
        """,
        (start_iso, end_iso),
    )[0]
    unsupported_language = db.fetchone(
        """
        SELECT COUNT(*) FROM ingest_queue
        WHERE created_at BETWEEN ? AND ?
          AND error_code = 'unsupported_language'
        """,
        (start_iso, end_iso),
    )[0]
    filtered_noise = db.fetchone(
        """
        SELECT COUNT(*) FROM ingest_queue
        WHERE created_at BETWEEN ? AND ?
          AND error_code = 'noise'
          AND file_size > 512
        """,
        (start_iso, end_iso),
    )[0]
    android_routing_alerts = db.fetchone(
        """
        SELECT COUNT(*) FROM client_signposts
        WHERE created_at BETWEEN ? AND ?
          AND route_kind = 'background_ws'
          AND debug_build = 1
          AND is_local_primary = 1
          AND decision = 'fallback_remote'
        """,
        (start_iso, end_iso),
    )[0]
    android_routing_ok = db.fetchone(
        """
        SELECT COUNT(*) FROM client_signposts
        WHERE created_at BETWEEN ? AND ?
          AND route_kind = 'background_ws'
          AND debug_build = 1
          AND is_local_primary = 1
          AND decision IN ('local_debug_pinned', 'primary_reachable', 'primary_direct')
        """,
        (start_iso, end_iso),
    )[0]

    signal_map = {
        "android_debug_falls_back_to_remote_when_local_alive": _build_incident_signal_state(
            state="alert"
            if android_routing_alerts > 0
            else ("ok" if android_routing_ok > 0 else "unknown"),
            value=int(android_routing_alerts if android_routing_alerts > 0 else android_routing_ok),
            source="client_signposts background_ws decision",
            details="Последние debug signpost-события Android по выбору background WebSocket route.",
        ),
        "ingest_stuck_received_without_transcription": _build_incident_signal_state(
            state="alert" if stale_received > 0 else "ok",
            value=int(stale_received),
            source="ingest_queue.status=received older than 30m",
            details="Сколько ingest зависло в received без транскрипции дольше 30 минут.",
        ),
        "enrichment_404_after_segment_complete": _build_incident_signal_state(
            state="alert" if missing_enrichment > 0 else "ok",
            value=int(missing_enrichment),
            source="event_ready without current structured_event",
            details="Сколько event_ready записей сегодня не имеют текущего structured_event.",
        ),
        "micro_wav_segments_under_min_size": _build_incident_signal_state(
            state="alert" if micro_segments > 0 else "ok",
            value=int(micro_segments),
            source="ingest_queue.file_size <= 512 bytes",
            details="Сколько сегментов за сегодня дошло до ingest с подозрительно маленьким WAV.",
        ),
        "unsupported_language_unknown_filters_valid_ru_audio": _build_incident_signal_state(
            state="alert" if unsupported_language > 0 else "ok",
            value=int(unsupported_language),
            source="ingest_queue.error_code = unsupported_language",
            details="Сколько сегментов за сегодня были отфильтрованы как unsupported_language.",
        ),
        "vad_noise_filtering_overrejects_valid_short_speech": _build_incident_signal_state(
            state="alert" if filtered_noise > 0 else "ok",
            value=int(filtered_noise),
            source="ingest_queue.error_code = noise with file_size > 512 bytes",
            details="Сколько немикро-сегментов за сегодня были отфильтрованы как noise после ASR.",
        ),
    }

    report_rows: list[dict[str, object]] = []
    alerting = 0
    healthy = 0
    unknown = 0
    for incident in incidents:
        if not isinstance(incident, dict):
            continue
        signature = str(incident.get("signature", "")).strip()
        signal = signal_map.get(
            signature,
            _build_incident_signal_state(
                state="unknown",
                value=None,
                source="no_runtime_mapping",
                details="Для этой сигнатуры ещё нет автоматического runtime signpost.",
            ),
        )
        if signal["state"] == "alert":
            alerting += 1
        elif signal["state"] == "ok":
            healthy += 1
        else:
            unknown += 1
        report_rows.append(
            {
                "incident_id": incident.get("incident_id"),
                "signature": signature,
                "title": incident.get("title"),
                "status": incident.get("status"),
                "signpost": incident.get("signpost"),
                "signal": signal,
            }
        )

    summary = build_incident_summary(payload)
    summary.update(
        {
            "alerting": alerting,
            "healthy": healthy,
            "unknown": unknown,
            "validation_errors": len(validation_errors),
        }
    )
    return {
        "summary": summary,
        "validation_errors": validation_errors,
        "incidents": report_rows,
    }


@router.post("/audio")
@limiter.limit(RateLimitConfig.INGEST_AUDIO_LIMIT)
async def ingest_audio(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    sync: bool = Query(default=False),
):
    """Принимает аудиофайл от edge-устройства и проводит полный unified pipeline."""
    safe_checker = get_safe_checker()

    try:
        if safe_checker:
            ext_valid, ext_reason = safe_checker.check_file_extension(
                Path(file.filename or "temp.wav")
            )
            if not ext_valid:
                logger.warning(
                    "safe_file_extension_check_failed", reason=ext_reason, filename=file.filename
                )
                if os.getenv("SAFE_MODE") == "strict":
                    raise HTTPException(
                        status_code=400, detail=f"SAFE validation failed: {ext_reason}"
                    )

        content = await file.read()

        if safe_checker:
            validate_safe_file_size(
                content=content,
                suffix=("." + (file.filename or "").split(".")[-1])
                if file.filename and "." in file.filename
                else "",
                safe_checker=safe_checker,
                safe_mode=os.getenv("SAFE_MODE", "audit"),
            )

        sync_process = sync or os.getenv("INGEST_SYNC_PROCESS", "0") == "1"
        run_enrichment = os.getenv("INGEST_SYNC_PROCESS", "0") == "1" and not sync

        unified = await process_audio_bytes(
            content=content,
            content_type=file.content_type,
            original_filename=file.filename,
            segment_id=request.headers.get("X-Segment-Id"),
            captured_at=request.headers.get("X-Captured-At"),
            ingest_stage="ingest_audio_received",
            transcription_stage="ingest_transcription_saved",
            run_enrichment=run_enrichment,
            fail_open=True,
            transcribe_now=sync_process,
        )

        # Backward-compatible envelope for existing clients.
        out = {
            "status": unified.get("status", "received"),
            "id": unified.get("ingest_id"),
            "filename": unified.get("filename"),
            "transcription_id": unified.get("transcription_id"),
            "reason": unified.get("reason"),
            "path": str(Path("uploads") / str(unified.get("filename", ""))),
            "size": len(content),
        }
        if unified.get("status") == "transcribed":
            payload = unified.get("result", {})
            out["transcription"] = {
                "text": payload.get("text", ""),
                "language": payload.get("language", ""),
                "privacy_mode": payload.get("privacy_mode", "audit"),
            }
        if unified.get("status") == "duplicate" and unified.get("result"):
            payload = unified.get("result", {})
            out["transcription"] = {
                "text": payload.get("text", ""),
                "language": payload.get("language", ""),
                "privacy_mode": payload.get("privacy_mode", "audit"),
            }
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("audio_upload_failed", error=str(e))
        # ПОЧЕМУ: str(e) не отдаём клиенту — утечка внутренней инфраструктуры.
        # Детали в логах (logger.error выше), клиент получает generic ошибку.
        raise HTTPException(status_code=500, detail="Failed to process audio. Check server logs.")


@router.get("/status/{file_id}")
async def get_ingest_status(file_id: str):
    """Проверяет статус обработки файла."""
    return {
        "id": file_id,
        "status": "pending",
        "message": "Use DB/metrics endpoint for precise status details",
    }


@router.get("/pipeline-status")
async def get_pipeline_status():
    """
    Диагностика пайплайна: запись → отправка → сервер → события.
    Для контролируемого теста: после одной записи проверить, вырос ли transcriptions_today.
    """
    from src.utils.date_utils import resolve_date_range
    from src.storage.db import get_reflexio_db

    db_path = settings.STORAGE_PATH / "reflexio.db"
    llm_circuit_breakers = _build_llm_circuit_breaker_state()
    if not db_path.exists():
        incident_status = {
            "summary": {
                "total": 0,
                "open": 0,
                "in_progress": 0,
                "closed": 0,
                "alerting": 0,
                "healthy": 0,
                "unknown": 0,
                "validation_errors": 0,
            },
            "validation_errors": [],
            "incidents": [],
        }
        ingest_health = {
            "stale_counts": {"received": 0, "asr_pending": 0},
            "recovery_counts": {"watchdog_retryable": 0, "asr_runtime_retryable": 0},
            "latency_ms": {"received_to_terminal_avg": None, "received_to_event_ready_avg": None},
        }
        return {
            "server_ok": True,
            "transcriptions_today": 0,
            "transcriptions_total": 0,
            "last_transcription_at": None,
            "ingest_queue": {
                "pending": 0,
                "processed": 0,
                "error": 0,
                "filtered": 0,
                "quarantine": 0,
            },
            "ingest_stage_counts": {},
            "episode_counts": {"open": 0, "closed": 0, "summarized": 0, "needs_review": 0},
            "day_thread_counts": {"total": 0, "trusted": 0, "low_confidence": 0},
            "long_thread_counts": {"total": 0, "active": 0, "resolved": 0},
            "quality_counts": {"trusted": 0, "uncertain": 0, "garbage": 0, "quarantined": 0},
            "ingest_health": ingest_health,
            "llm_circuit_breakers": llm_circuit_breakers,
            "memory_health": {
                "trusted_fraction": 0.0,
                "review_fraction": 0.0,
                "thread_coverage": 0.0,
                "digest_incomplete_context_total": 0,
                "degraded_digest_candidate": False,
            },
            "slo_state": {
                "status": "healthy",
                "alerts": [],
                "beta_thresholds": {
                    "min_trusted_fraction": 0.5,
                    "max_review_fraction": 0.5,
                    "min_thread_coverage": 0.5,
                    "max_digest_incomplete_context_total": 0,
                },
                "snapshot": {
                    "trusted_fraction": 0.0,
                    "review_fraction": 0.0,
                    "thread_coverage": 0.0,
                    "digest_incomplete_context_total": 0,
                    "episodes_summarized": 0,
                    "day_threads_trusted": 0,
                    "stale_received": 0,
                    "stale_asr_pending": 0,
                },
            },
            "incident_status": incident_status,
            "golden_path": _build_golden_path_contract(
                server_ok=True,
                transcriptions_total=0,
                ingest_health=ingest_health,
                incident_status=incident_status,
            ),
        }

    db = get_reflexio_db(db_path)
    dr = resolve_date_range()
    start_iso, end_iso = dr.sql_range()
    llm_circuit_breakers = _build_llm_circuit_breaker_state()

    try:
        today_count = db.fetchone(
            "SELECT COUNT(*) FROM transcriptions WHERE created_at BETWEEN ? AND ?",
            (start_iso, end_iso),
        )[0]
        total = db.fetchone("SELECT COUNT(*) FROM transcriptions")[0]
        last_row = db.fetchone(
            "SELECT created_at FROM transcriptions ORDER BY created_at DESC LIMIT 1"
        )
        last_at = last_row[0] if last_row and last_row[0] else None
        q = {
            "pending": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status IN ('pending','received','deduplicated','asr_pending','event_pending','transcribed')"
            )[0],
            "processed": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status IN ('processed','event_ready')"
            )[0],
            "error": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status IN ('error','retryable_error')"
            )[0],
            "filtered": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'filtered'")[
                0
            ],
            "quarantine": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status = 'quarantined'"
            )[0],
        }
        stage_counts = {
            "received": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'received'")[
                0
            ],
            "deduplicated": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE transport_status = 'deduplicated'"
            )[0],
            "asr_pending": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status = 'asr_pending'"
            )[0],
            "transcribed": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status = 'transcribed'"
            )[0],
            "event_pending": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status = 'event_pending'"
            )[0],
            "event_ready": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status = 'event_ready'"
            )[0],
            "retryable_error": db.fetchone(
                "SELECT COUNT(*) FROM ingest_queue WHERE status = 'retryable_error'"
            )[0],
            "quarantined": q["quarantine"],
        }
        episode_counts = {
            "open": db.fetchone("SELECT COUNT(*) FROM episodes WHERE status = 'open'")[0],
            "closed": db.fetchone("SELECT COUNT(*) FROM episodes WHERE status = 'closed'")[0],
            "summarized": db.fetchone("SELECT COUNT(*) FROM episodes WHERE status = 'summarized'")[
                0
            ],
            "needs_review": db.fetchone("SELECT COUNT(*) FROM episodes WHERE needs_review = 1")[0],
        }
        day_thread_counts = {
            "total": db.fetchone("SELECT COUNT(*) FROM day_threads")[0],
            "trusted": db.fetchone(
                "SELECT COUNT(*) FROM day_threads WHERE thread_confidence >= 0.7"
            )[0],
            "low_confidence": db.fetchone(
                "SELECT COUNT(*) FROM day_threads WHERE thread_confidence < 0.7"
            )[0],
        }
        long_thread_counts = {
            "total": db.fetchone("SELECT COUNT(*) FROM long_threads")[0],
            "active": db.fetchone("SELECT COUNT(*) FROM long_threads WHERE status = 'active'")[0],
            "resolved": db.fetchone("SELECT COUNT(*) FROM long_threads WHERE status = 'resolved'")[
                0
            ],
        }
        quality_counts = {
            "trusted": db.fetchone("SELECT COUNT(*) FROM episodes WHERE quality_state = 'trusted'")[
                0
            ],
            "uncertain": db.fetchone(
                "SELECT COUNT(*) FROM episodes WHERE quality_state = 'uncertain'"
            )[0],
            "garbage": db.fetchone("SELECT COUNT(*) FROM episodes WHERE quality_state = 'garbage'")[
                0
            ],
            "quarantined": db.fetchone(
                "SELECT COUNT(*) FROM episodes WHERE quality_state = 'quarantined'"
            )[0],
        }
        stale_counts = {
            "received": db.fetchone(
                """
                SELECT COUNT(*) FROM ingest_queue
                WHERE status = 'received'
                  AND created_at < datetime('now', '-30 minutes')
                """
            )[0],
            "asr_pending": db.fetchone(
                """
                SELECT COUNT(*) FROM ingest_queue
                WHERE status = 'asr_pending'
                  AND created_at < datetime('now', '-45 minutes')
                """
            )[0],
        }
        recovery_counts = {
            "watchdog_retryable": db.fetchone(
                """
                SELECT COUNT(*) FROM ingest_queue
                WHERE status = 'retryable_error'
                  AND error_code IN (
                    'watchdog_stuck_pending',
                    'watchdog_stuck_received',
                    'watchdog_stuck_asr_pending'
                  )
                """
            )[0],
            "asr_runtime_retryable": db.fetchone(
                """
                SELECT COUNT(*) FROM ingest_queue
                WHERE status = 'retryable_error'
                  AND error_code = 'asr_runtime_error'
                """
            )[0],
        }
        received_to_terminal_avg = db.fetchone(
            """
            SELECT AVG((julianday(processed_at) - julianday(created_at)) * 86400000.0)
            FROM ingest_queue
            WHERE processed_at IS NOT NULL
              AND status IN ('transcribed', 'event_ready', 'retryable_error', 'quarantined', 'filtered')
            """
        )[0]
        received_to_event_ready_avg = db.fetchone(
            """
            SELECT AVG((julianday(processed_at) - julianday(created_at)) * 86400000.0)
            FROM ingest_queue
            WHERE processed_at IS NOT NULL
              AND status = 'event_ready'
            """
        )[0]
        ingest_health = {
            "stale_counts": stale_counts,
            "recovery_counts": recovery_counts,
            "latency_ms": {
                "received_to_terminal_avg": _round_maybe(received_to_terminal_avg),
                "received_to_event_ready_avg": _round_maybe(received_to_event_ready_avg),
            },
        }
        digest_rows = db.fetchall("SELECT digest_json FROM digest_cache")
        digest_incomplete_context_total = 0
        for row in digest_rows:
            try:
                payload = json.loads(row["digest_json"] or "{}")
            except Exception:
                continue
            if payload.get("incomplete_context") or payload.get("degraded"):
                digest_incomplete_context_total += 1
        trusted_total = quality_counts["trusted"]
        review_total = (
            quality_counts["uncertain"] + quality_counts["garbage"] + quality_counts["quarantined"]
        )
        quality_total = trusted_total + review_total
        summarized_total = episode_counts["summarized"]
        trusted_threads = day_thread_counts["trusted"]
        memory_health = {
            "trusted_fraction": round((trusted_total / quality_total), 3) if quality_total else 0.0,
            "review_fraction": round((review_total / quality_total), 3) if quality_total else 0.0,
            "thread_coverage": round((trusted_threads / summarized_total), 3)
            if summarized_total
            else 0.0,
            "digest_incomplete_context_total": digest_incomplete_context_total,
            "degraded_digest_candidate": bool(
                digest_incomplete_context_total > 0
                or quality_counts["uncertain"] > 0
                or quality_counts["quarantined"] > 0
            ),
        }
        slo_state = _build_slo_state(
            ingest_queue=q,
            episode_counts=episode_counts,
            day_thread_counts=day_thread_counts,
            quality_counts=quality_counts,
            memory_health=memory_health,
            ingest_health=ingest_health,
        )
        incident_status = _build_incident_status_report(db, start_iso=start_iso, end_iso=end_iso)
        golden_path = _build_golden_path_contract(
            server_ok=True,
            transcriptions_total=total,
            ingest_health=ingest_health,
            incident_status=incident_status,
        )
    except Exception as e:
        logger.warning("pipeline_status_failed", error=str(e))
        incident_status = {
            "summary": {
                "total": 0,
                "open": 0,
                "in_progress": 0,
                "closed": 0,
                "alerting": 0,
                "healthy": 0,
                "unknown": 0,
                "validation_errors": 0,
            },
            "validation_errors": [],
            "incidents": [],
        }
        ingest_health = {
            "stale_counts": {"received": 0, "asr_pending": 0},
            "recovery_counts": {"watchdog_retryable": 0, "asr_runtime_retryable": 0},
            "latency_ms": {"received_to_terminal_avg": None, "received_to_event_ready_avg": None},
        }
        return {
            "server_ok": True,
            "transcriptions_today": 0,
            "transcriptions_total": 0,
            "last_transcription_at": None,
            "ingest_queue": {
                "pending": 0,
                "processed": 0,
                "error": 0,
                "filtered": 0,
                "quarantine": 0,
            },
            "ingest_stage_counts": {},
            "episode_counts": {"open": 0, "closed": 0, "summarized": 0, "needs_review": 0},
            "day_thread_counts": {"total": 0, "trusted": 0, "low_confidence": 0},
            "long_thread_counts": {"total": 0, "active": 0, "resolved": 0},
            "quality_counts": {"trusted": 0, "uncertain": 0, "garbage": 0, "quarantined": 0},
            "ingest_health": ingest_health,
            "llm_circuit_breakers": llm_circuit_breakers,
            "memory_health": {
                "trusted_fraction": 0.0,
                "review_fraction": 0.0,
                "thread_coverage": 0.0,
                "digest_incomplete_context_total": 0,
                "degraded_digest_candidate": False,
            },
            "slo_state": {
                "status": "healthy",
                "alerts": [],
                "beta_thresholds": {
                    "min_trusted_fraction": 0.5,
                    "max_review_fraction": 0.5,
                    "min_thread_coverage": 0.5,
                    "max_digest_incomplete_context_total": 0,
                },
                "snapshot": {
                    "trusted_fraction": 0.0,
                    "review_fraction": 0.0,
                    "thread_coverage": 0.0,
                    "digest_incomplete_context_total": 0,
                    "episodes_summarized": 0,
                    "day_threads_trusted": 0,
                    "stale_received": 0,
                    "stale_asr_pending": 0,
                },
            },
            "incident_status": incident_status,
            "golden_path": _build_golden_path_contract(
                server_ok=True,
                transcriptions_total=0,
                ingest_health=ingest_health,
                incident_status=incident_status,
            ),
            "_error": str(e),
        }

    return {
        "server_ok": True,
        "transcriptions_today": today_count,
        "transcriptions_total": total,
        "last_transcription_at": last_at,
        "ingest_queue": q,
        "ingest_stage_counts": stage_counts,
        "episode_counts": episode_counts,
        "day_thread_counts": day_thread_counts,
        "long_thread_counts": long_thread_counts,
        "quality_counts": quality_counts,
        "ingest_health": ingest_health,
        "llm_circuit_breakers": llm_circuit_breakers,
        "memory_health": memory_health,
        "slo_state": slo_state,
        "incident_status": incident_status,
        "golden_path": golden_path,
    }


@router.get("/incident-status")
async def get_incident_status():
    """Возвращает incident ledger с runtime signpost-сигналами."""
    from src.utils.date_utils import resolve_date_range
    from src.storage.db import get_reflexio_db

    payload = load_incident_ledger()
    validation_errors = validate_incident_ledger(payload)
    db_path = settings.STORAGE_PATH / "reflexio.db"
    if not db_path.exists():
        return {
            "summary": {
                **build_incident_summary(payload),
                "alerting": 0,
                "healthy": 0,
                "unknown": len(payload.get("incidents", [])),
                "validation_errors": len(validation_errors),
            },
            "validation_errors": validation_errors,
            "incidents": [
                {
                    "incident_id": incident.get("incident_id"),
                    "signature": incident.get("signature"),
                    "title": incident.get("title"),
                    "status": incident.get("status"),
                    "signpost": incident.get("signpost"),
                    "signal": {
                        "state": "unknown",
                        "value": None,
                        "source": "storage_missing",
                        "details": "Локальная БД не найдена, runtime signpost недоступен.",
                    },
                }
                for incident in payload.get("incidents", [])
                if isinstance(incident, dict)
            ],
        }

    db = get_reflexio_db(db_path)
    dr = resolve_date_range()
    start_iso, end_iso = dr.sql_range()
    try:
        return _build_incident_status_report(db, start_iso=start_iso, end_iso=end_iso)
    except Exception as e:
        logger.warning("incident_status_failed", error=str(e))
        return {
            "summary": {
                **build_incident_summary(payload),
                "alerting": 0,
                "healthy": 0,
                "unknown": len(payload.get("incidents", [])),
                "validation_errors": len(validation_errors),
            },
            "validation_errors": validation_errors,
            "incidents": [],
            "_error": str(e),
        }


@router.post("/client-signpost")
async def ingest_client_signpost(payload: ClientSignpostRequest):
    """Сохраняет runtime signpost от мобильного клиента."""
    from src.storage.db import get_reflexio_db

    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    event_id = f"client-signpost-{uuid.uuid4()}"
    created_at = datetime.now(timezone.utc).isoformat()
    with db.transaction():
        db.execute(
            """
            INSERT INTO client_signposts (
                id, source, route_kind, primary_url, resolved_url, decision,
                is_local_primary, debug_build, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                payload.source,
                payload.route_kind,
                payload.primary_url,
                payload.resolved_url,
                payload.decision,
                1 if payload.is_local_primary else 0,
                1 if payload.debug_build else 0,
                created_at,
            ),
        )
    return {"status": "ok", "id": event_id}


@router.get("/pipeline-trends")
async def get_pipeline_trends(days_back: int = 7):
    """Read-only trends for recent episodic memory health by day."""
    days_back = max(1, min(days_back, 30))
    db_path = settings.STORAGE_PATH / "reflexio.db"
    if not db_path.exists():
        return {"days_back": days_back, "recent_days": []}

    from src.storage.db import get_reflexio_db

    db = get_reflexio_db(db_path)
    try:
        recent_days = _build_recent_day_trends(db, days_back=days_back)
    except Exception as e:
        logger.warning("pipeline_trends_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to build pipeline trends") from e

    return {
        "days_back": days_back,
        "recent_days": recent_days,
    }


@router.post("/reprocess/{file_id}")
async def reprocess_ingest(file_id: str):
    """Requeue quarantined/retryable ingest items without shell-level DB edits."""
    from src.api.routers.websocket import get_ingest_result_registry
    from src.storage.db import get_reflexio_db

    db_path = settings.STORAGE_PATH / "reflexio.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Ingest item not found")

    db = get_reflexio_db(db_path)
    row = db.fetchone(
        """
        SELECT id, file_path, status, created_at FROM ingest_queue
        WHERE id = ?
        LIMIT 1
        """,
        (file_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Ingest item not found")

    stale_reprocessable = {"received", "asr_pending"}
    if row["status"] not in {"retryable_error", "quarantined"} and not (
        row["status"] in stale_reprocessable and _is_stale_for_reprocess(row["created_at"])
    ):
        raise HTTPException(status_code=409, detail="Ingest item is not reprocessable")

    file_path = Path(row["file_path"])
    if not file_path.exists():
        with db.transaction():
            db.execute(
                """
                UPDATE ingest_queue
                SET status='quarantined',
                    processing_status='quarantined',
                    error_code='missing_audio',
                    quarantine_reason='missing_audio',
                    error_message='Audio artifact missing'
                WHERE id=?
                """,
                (file_id,),
            )
        raise HTTPException(status_code=409, detail="Audio artifact missing")

    with db.transaction():
        db.execute(
            """
            UPDATE ingest_queue
            SET status='received',
                processing_status='received',
                error_code=NULL,
                error_message=NULL,
                quarantine_reason=NULL,
                processed_at=NULL
            WHERE id=?
            """,
            (file_id,),
        )

    worker = get_ingest_worker(get_ingest_result_registry())
    worker.submit(
        IngestTask(
            ingest_id=file_id,
            file_path=file_path,
            connection_id="reprocess",
            enrichment_prefix=None,
        )
    )
    return {"id": file_id, "status": "requeued"}
