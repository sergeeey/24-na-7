"""Роутер для загрузки и обработки аудио."""
import os
import uuid
import tempfile
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.utils.config import settings
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitConfig
from src.api.middleware.safe_middleware import get_safe_checker

logger = get_logger("api.ingest")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/audio")
@limiter.limit(RateLimitConfig.INGEST_AUDIO_LIMIT)
async def ingest_audio(request: Request, response: Response, file: UploadFile = File(...)):
    """
    Принимает аудиофайл от edge-устройства.
    
    Сохраняет файл в storage/uploads/ и возвращает ID для отслеживания.
    SAFE проверки: размер файла, расширение, PII в метаданных.
    
    **Пример запроса:**
    ```bash
    curl -X POST "http://localhost:8000/ingest/audio" \\
         -H "Content-Type: multipart/form-data" \\
         -F "file=@audio.wav"
    ```
    
    **Пример ответа:**
    ```json
    {
        "status": "received",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "filename": "20240217_120000_550e8400-e29b-41d4-a716-446655440000.wav",
        "path": "/path/to/storage/uploads/20240217_120000_550e8400-e29b-41d4-a716-446655440000.wav",
        "size": 1024000
    }
    ```
    """
    safe_checker = get_safe_checker()
    
    try:
        # SAFE: Проверка расширения файла
        if safe_checker:
            from pathlib import Path as PathLib
            temp_path = PathLib(file.filename or "temp.wav")
            ext_valid, ext_reason = safe_checker.check_file_extension(temp_path)
            if not ext_valid:
                logger.warning("safe_file_extension_check_failed", reason=ext_reason, filename=file.filename)
                if os.getenv("SAFE_MODE") == "strict":
                    raise HTTPException(status_code=400, detail=f"SAFE validation failed: {ext_reason}")
        
        # Читаем содержимое файла
        content = await file.read()
        file_size = len(content)
        
        # SAFE: Проверка размера файла
        if safe_checker:
            from pathlib import Path as PathLib
            with tempfile.NamedTemporaryFile(delete=False, suffix=PathLib(file.filename or "").suffix) as temp_file:
                temp_file.write(content)
                temp_path = PathLib(temp_file.name)
            # Закрываем файл перед unlink (на Windows нельзя удалить открытый файл)
            try:
                size_valid, size_reason = safe_checker.check_file_size(temp_path)
            finally:
                temp_path.unlink(missing_ok=True)
            if not size_valid:
                logger.warning("safe_file_size_check_failed", reason=size_reason, size=file_size)
                if os.getenv("SAFE_MODE") == "strict":
                    raise HTTPException(status_code=400, detail=f"SAFE validation failed: {size_reason}")
        
        # Генерируем уникальное имя файла
        file_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file_id}.wav"
        dest_path = settings.UPLOADS_PATH / filename
        
        # Сохраняем файл
        dest_path.write_bytes(content)
        
        logger.info(
            "audio_received",
            filename=filename,
            size=file_size,
            content_type=file.content_type,
            safe_validation="passed" if safe_checker else "disabled",
        )
        
        return {
            "status": "received",
            "id": file_id,
            "filename": filename,
            "path": str(dest_path),
            "size": file_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("audio_upload_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save audio: {str(e)}")


@router.get("/status/{file_id}")
async def get_ingest_status(file_id: str):
    """
    Проверяет статус обработки файла.
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/ingest/status/550e8400-e29b-41d4-a716-446655440000"
    ```
    
    **Пример ответа:**
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "pending",
        "message": "File received, processing will be implemented in next iteration"
    }
    ```
    """
    # В MVP всегда возвращаем pending, в будущем будем отслеживать статус
    return {
        "id": file_id,
        "status": "pending",
        "message": "File received, processing will be implemented in next iteration",
    }
