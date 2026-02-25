"""Роутер для загрузки и обработки аудио."""
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.middleware.safe_middleware import get_safe_checker
from src.core.audio_processing import process_audio_bytes, validate_safe_file_size
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







