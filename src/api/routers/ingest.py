"""Роутер для загрузки и обработки аудио."""
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.middleware.safe_middleware import get_safe_checker
from src.core.audio_processing import process_audio_bytes, validate_safe_file_size
from src.ingest.worker import IngestTask, get_ingest_worker
from src.utils.config import settings  # noqa: F401
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitConfig

logger = get_logger("api.ingest")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/audio")
@limiter.limit(RateLimitConfig.INGEST_AUDIO_LIMIT)
async def ingest_audio(request: Request, response: Response, file: UploadFile = File(...)):
    """Принимает аудиофайл от edge-устройства и проводит полный unified pipeline."""
    safe_checker = get_safe_checker()

    try:
        if safe_checker:
            ext_valid, ext_reason = safe_checker.check_file_extension(Path(file.filename or "temp.wav"))
            if not ext_valid:
                logger.warning("safe_file_extension_check_failed", reason=ext_reason, filename=file.filename)
                if os.getenv("SAFE_MODE") == "strict":
                    raise HTTPException(status_code=400, detail=f"SAFE validation failed: {ext_reason}")

        content = await file.read()

        if safe_checker:
            validate_safe_file_size(
                content=content,
                suffix=("." + (file.filename or "").split(".")[-1]) if file.filename and "." in file.filename else "",
                safe_checker=safe_checker,
                safe_mode=os.getenv("SAFE_MODE", "audit"),
            )

        sync_process = os.getenv("INGEST_SYNC_PROCESS", "0") == "1"

        unified = await process_audio_bytes(
            content=content,
            content_type=file.content_type,
            original_filename=file.filename,
            segment_id=request.headers.get("X-Segment-Id"),
            captured_at=request.headers.get("X-Captured-At"),
            ingest_stage="ingest_audio_received",
            transcription_stage="ingest_transcription_saved",
            run_enrichment=sync_process,
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
    if not db_path.exists():
        return {
            "server_ok": True,
            "transcriptions_today": 0,
            "transcriptions_total": 0,
            "last_transcription_at": None,
            "ingest_queue": {"pending": 0, "processed": 0, "error": 0, "filtered": 0, "quarantine": 0},
            "ingest_stage_counts": {},
            "episode_counts": {"open": 0, "closed": 0, "summarized": 0, "needs_review": 0},
        }

    db = get_reflexio_db(db_path)
    dr = resolve_date_range()
    start_iso, end_iso = dr.sql_range()

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
            "filtered": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'filtered'")[0],
            "quarantine": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'quarantined'")[0],
        }
        stage_counts = {
            "received": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'received'")[0],
            "deduplicated": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE transport_status = 'deduplicated'")[0],
            "asr_pending": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'asr_pending'")[0],
            "transcribed": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'transcribed'")[0],
            "event_pending": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'event_pending'")[0],
            "event_ready": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'event_ready'")[0],
            "retryable_error": db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'retryable_error'")[0],
            "quarantined": q["quarantine"],
        }
        episode_counts = {
            "open": db.fetchone("SELECT COUNT(*) FROM episodes WHERE status = 'open'")[0],
            "closed": db.fetchone("SELECT COUNT(*) FROM episodes WHERE status = 'closed'")[0],
            "summarized": db.fetchone("SELECT COUNT(*) FROM episodes WHERE status = 'summarized'")[0],
            "needs_review": db.fetchone("SELECT COUNT(*) FROM episodes WHERE needs_review = 1")[0],
        }
    except Exception as e:
        logger.warning("pipeline_status_failed", error=str(e))
        return {
            "server_ok": True,
            "transcriptions_today": 0,
            "transcriptions_total": 0,
            "last_transcription_at": None,
            "ingest_queue": {"pending": 0, "processed": 0, "error": 0, "filtered": 0, "quarantine": 0},
            "ingest_stage_counts": {},
            "episode_counts": {"open": 0, "closed": 0, "summarized": 0, "needs_review": 0},
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
        SELECT id, file_path, status FROM ingest_queue
        WHERE id = ?
        LIMIT 1
        """,
        (file_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Ingest item not found")

    if row["status"] not in {"retryable_error", "quarantined"}:
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







