"""Роутер для транскрипции аудио."""
import json
import sqlite3
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from src.asr.transcribe import transcribe_audio
from src.memory.semantic_memory import consolidate_to_memory_node, ensure_semantic_memory_tables
from src.security.privacy_pipeline import apply_privacy_mode
from src.storage.ingest_persist import ensure_ingest_tables
from src.storage.integrity import append_integrity_event, ensure_integrity_tables
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api.asr")
router = APIRouter(prefix="/asr", tags=["asr"])


@router.post("/transcribe")
async def transcribe_endpoint(file_id: str = Query(..., description="ID файла для транскрипции")):
    """Транскрибирует загруженный аудиофайл по его ID."""
    try:
        matching_files = list(settings.UPLOADS_PATH.glob(f"*_{file_id}.wav"))
        if not matching_files:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

        audio_path = matching_files[0]
        logger.info("transcription_started", file_id=file_id, path=str(audio_path))

        result = transcribe_audio(audio_path, language=settings.ASR_LANGUAGE)

        privacy = apply_privacy_mode(result.get("text", ""), mode=settings.PRIVACY_MODE)
        if not privacy.allowed:
            raise HTTPException(status_code=422, detail="PII blocked by privacy policy")

        result["text"] = privacy.text
        result["privacy_mode"] = privacy.mode
        result["pii_count"] = privacy.pii_count

        db_path = settings.STORAGE_PATH / "reflexio.db"
        ensure_ingest_tables(db_path)
        ensure_integrity_tables(db_path)
        ensure_semantic_memory_tables(db_path)

        trans_id = str(uuid.uuid4())
        segments_json = json.dumps(result.get("segments", []), ensure_ascii=False)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transcriptions (
                id TEXT PRIMARY KEY, ingest_id TEXT NOT NULL,
                text TEXT NOT NULL, language TEXT,
                language_probability REAL, duration REAL,
                segments TEXT, created_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO transcriptions (id, ingest_id, text, language, language_probability, duration, segments, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trans_id,
                file_id,
                result.get("text", ""),
                result.get("language"),
                result.get("language_probability"),
                result.get("duration"),
                segments_json,
                datetime.now().isoformat(),
            ),
        )
        conn.execute(
            "UPDATE ingest_queue SET status='processed', processed_at=? WHERE id=?",
            (datetime.now().isoformat(), file_id),
        )
        conn.commit()
        conn.close()

        if settings.INTEGRITY_CHAIN_ENABLED:
            append_integrity_event(
                db_path=db_path,
                ingest_id=file_id,
                stage="asr_transcription_saved",
                payload_text=result.get("text", ""),
                metadata={"transcription_id": trans_id, "language": result.get("language", "")},
            )

        if settings.MEMORY_ENABLED:
            consolidate_to_memory_node(
                db_path=db_path,
                ingest_id=file_id,
                transcription_id=trans_id,
                text=result.get("text", ""),
                summary="",
                topics=[],
            )

        logger.info("transcription_saved_to_db", file_id=file_id, transcription_id=trans_id)

        return {
            "status": "success",
            "file_id": file_id,
            "transcription_id": trans_id,
            "transcription": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("transcription_failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
