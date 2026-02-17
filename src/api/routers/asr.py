"""Роутер для транскрипции аудио."""
from fastapi import APIRouter, HTTPException, Query

from src.utils.config import settings
from src.utils.logging import get_logger
from src.asr.transcribe import transcribe_audio

logger = get_logger("api.asr")
router = APIRouter(prefix="/asr", tags=["asr"])


@router.post("/transcribe")
async def transcribe_endpoint(file_id: str = Query(..., description="ID файла для транскрипции")):
    """
    Транскрибирует загруженный аудиофайл по его ID.
    
    Ищет файл в storage/uploads/ по ID из имени файла.
    
    **Пример запроса:**
    ```bash
    curl -X POST "http://localhost:8000/asr/transcribe?file_id=550e8400-e29b-41d4-a716-446655440000"
    ```
    
    **Пример ответа:**
    ```json
    {
        "status": "success",
        "file_id": "550e8400-e29b-41d4-a716-446655440000",
        "transcription": {
            "text": "Привет, это тестовая транскрипция",
            "language": "ru",
            "segments": [...]
        }
    }
    ```
    
    **Ошибки:**
    - `404`: Файл не найден
    - `500`: Ошибка транскрипции
    """
    try:
        # Ищем файл по ID в имени
        matching_files = list(settings.UPLOADS_PATH.glob(f"*_{file_id}.wav"))
        if not matching_files:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")
        
        audio_path = matching_files[0]
        
        logger.info("transcription_started", file_id=file_id, path=str(audio_path))
        
        # Транскрибируем
        result = transcribe_audio(audio_path)
        
        return {
            "status": "success",
            "file_id": file_id,
            "transcription": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("transcription_failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
