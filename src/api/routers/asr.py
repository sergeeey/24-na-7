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

        # ПОЧЕМУ: сохраняем транскрипцию в SQLite чтобы digest мог её найти
        # Раньше результат только возвращался клиенту, но не сохранялся
        try:
            import sqlite3, uuid, json
            from datetime import datetime
            db_path = settings.STORAGE_PATH / "reflexio.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id TEXT PRIMARY KEY, ingest_id TEXT NOT NULL,
                    text TEXT NOT NULL, language TEXT,
                    language_probability REAL, duration REAL,
                    segments TEXT, created_at TEXT
                )
            """)
            trans_id = str(uuid.uuid4())
            segments_json = json.dumps(result.get("segments", []))
            conn.execute(
                "INSERT OR IGNORE INTO transcriptions (id, ingest_id, text, language, language_probability, duration, segments, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (trans_id, file_id, result.get("text", ""), result.get("language"),
                 result.get("language_probability"), result.get("duration"),
                 segments_json, datetime.now().isoformat()),
            )
            # Обновляем статус ingest_queue
            conn.execute(
                "UPDATE ingest_queue SET status='processed', processed_at=? WHERE id=?",
                (datetime.now().isoformat(), file_id),
            )
            conn.commit()
            conn.close()
            logger.info("transcription_saved_to_db", file_id=file_id, transcription_id=trans_id)
        except Exception as db_err:
            logger.warning("transcription_db_save_failed", error=str(db_err))

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
