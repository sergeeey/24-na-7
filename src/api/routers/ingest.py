"""Роутер для загрузки и обработки аудио."""
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.middleware.safe_middleware import get_safe_checker
from src.storage.ingest_persist import ensure_ingest_tables
from src.storage.integrity import append_integrity_event, ensure_integrity_tables
from src.utils.config import settings
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitConfig

logger = get_logger("api.ingest")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/ingest", tags=["ingest"])

_ALLOWED_WAV_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/vnd.wave",
    "application/octet-stream",
}


def _is_wav_bytes(content: bytes) -> bool:
    """Минимальная проверка WAV по magic bytes (RIFF/WAVE)."""
    if len(content) < 12:
        return False
    return content[:4] == b"RIFF" and content[8:12] == b"WAVE"


@router.post("/audio")
@limiter.limit(RateLimitConfig.INGEST_AUDIO_LIMIT)
async def ingest_audio(request: Request, response: Response, file: UploadFile = File(...)):
    """Принимает аудиофайл от edge-устройства."""
    safe_checker = get_safe_checker()

    try:
        if safe_checker:
            temp_path = Path(file.filename or "temp.wav")
            ext_valid, ext_reason = safe_checker.check_file_extension(temp_path)
            if not ext_valid:
                logger.warning("safe_file_extension_check_failed", reason=ext_reason, filename=file.filename)
                if os.getenv("SAFE_MODE") == "strict":
                    raise HTTPException(status_code=400, detail=f"SAFE validation failed: {ext_reason}")

        content = await file.read()
        file_size = len(content)

        if file.content_type and file.content_type not in _ALLOWED_WAV_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported content type: {file.content_type}")

        if not _is_wav_bytes(content):
            raise HTTPException(status_code=400, detail="Invalid WAV file signature")

        if safe_checker:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "").suffix) as temp_file:
                temp_file.write(content)
                temp_path = Path(temp_file.name)
            try:
                size_valid, size_reason = safe_checker.check_file_size(temp_path)
            finally:
                temp_path.unlink(missing_ok=True)
            if not size_valid:
                logger.warning("safe_file_size_check_failed", reason=size_reason, size=file_size)
                if os.getenv("SAFE_MODE") == "strict":
                    raise HTTPException(status_code=400, detail=f"SAFE validation failed: {size_reason}")

        file_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file_id}.wav"
        dest_path = settings.UPLOADS_PATH / filename
        dest_path.write_bytes(content)

        db_path = settings.STORAGE_PATH / "reflexio.db"
        ensure_ingest_tables(db_path)
        ensure_integrity_tables(db_path)

        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "INSERT OR IGNORE INTO ingest_queue (id, filename, file_path, file_size, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                (file_id, filename, str(dest_path), file_size, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as db_err:
            logger.warning("ingest_db_save_failed", error=str(db_err))

        if settings.INTEGRITY_CHAIN_ENABLED:
            append_integrity_event(
                db_path=db_path,
                ingest_id=file_id,
                stage="ingest_audio_received",
                payload_bytes=content,
                metadata={"filename": filename, "size": file_size, "content_type": file.content_type or ""},
            )

        logger.info(
            "audio_received",
            filename=filename,
            size=file_size,
            content_type=file.content_type,
            safe_validation="passed" if safe_checker else "disabled",
        )

        public_path = str(Path("uploads") / filename)
        return {
            "status": "received",
            "id": file_id,
            "filename": filename,
            "path": public_path,
            "size": file_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("audio_upload_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save audio: {str(e)}")


@router.get("/status/{file_id}")
async def get_ingest_status(file_id: str):
    """Проверяет статус обработки файла."""
    return {
        "id": file_id,
        "status": "pending",
        "message": "File received, processing will be implemented in next iteration",
    }
