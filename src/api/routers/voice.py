"""Роутер для голосовых операций: intent recognition + voice enrollment."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api.voice")
router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/intent")
async def recognize_intent(request: Request):
    """
    Распознавание intent через Voiceflow RAG или GPT-mini fallback.

    **Тело запроса:**
    ```json
    {
        "text": "текст для распознавания intent",
        "user_id": "user123"
    }
    ```
    """
    try:
        body = await request.json()
        text = body.get("text", "")
        user_id = body.get("user_id", "default")

        if not text:
            raise HTTPException(status_code=400, detail="text is required")

        from src.voice_agent.voiceflow_rag import get_voiceflow_client

        client = get_voiceflow_client()
        result = client.recognize_intent(text, user_id=user_id)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("intent_recognition_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Intent recognition failed")


@router.post("/enroll")
async def enroll_voice(
    files: List[UploadFile] = File(...),
    user_id: str = "default",
):
    """Создаёт голосовой профиль пользователя из нескольких WAV образцов.

    Требования:
    - Минимум 3 WAV файла с чистой речью пользователя
    - Каждый образец: 3-10 секунд, 16kHz, говорите естественно

    После создания профиля включите в .env: SPEAKER_VERIFICATION_ENABLED=true

    **Пример запроса:**
    ```bash
    curl -X POST "http://localhost:8000/voice/enroll" \\
         -H "Authorization: Bearer YOUR_KEY" \\
         -F "files=@sample1.wav" \\
         -F "files=@sample2.wav" \\
         -F "files=@sample3.wav"
    ```

    **Ответ:**
    ```json
    {
        "profile_id": "uuid",
        "user_id": "default",
        "sample_count": 3,
        "message": "Voice profile created successfully"
    }
    ```
    """
    min_samples = settings.SPEAKER_MIN_ENROLLMENT_SAMPLES

    if len(files) < min_samples:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Need at least {min_samples} voice samples, got {len(files)}. "
                "Record yourself speaking naturally for 3-10 seconds each."
            ),
        )

    # Проверяем content type
    for f in files:
        ct = f.content_type or ""
        if ct and not (ct.startswith("audio/") or ct == "application/octet-stream"):
            raise HTTPException(
                status_code=400,
                detail=f"File '{f.filename}': unsupported type '{ct}'. Use WAV audio.",
            )

    db_path = settings.STORAGE_PATH / "reflexio.db"
    tmp_paths: List[Path] = []

    try:
        # Сохраняем временные файлы для обработки
        for upload in files:
            content = await upload.read()
            if len(content) < 44:
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{upload.filename}' is too small to be a valid WAV",
                )
            # Проверяем RIFF/WAVE magic bytes
            if not (content[:4] == b"RIFF" and content[8:12] == b"WAVE"):
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{upload.filename}' is not a valid WAV file",
                )
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp.write(content)
                tmp_paths.append(Path(tmp.name))

        # Создаём голосовой профиль
        from src.speaker.enrollment import enroll_from_wavs

        result = enroll_from_wavs(
            wav_paths=tmp_paths,
            db_path=db_path,
            user_id=user_id,
        )

        return {
            **result,
            "message": (
                "Voice profile created successfully. "
                "Set SPEAKER_VERIFICATION_ENABLED=true in .env to activate filtering."
            ),
        }

    except ValueError as e:
        # Validation errors (too short samples, too few)
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("voice_enrollment_failed", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="Voice enrollment failed")
    finally:
        # Всегда удаляем временные файлы
        for tmp_path in tmp_paths:
            tmp_path.unlink(missing_ok=True)


@router.get("/enroll/status")
async def enrollment_status(user_id: str = "default"):
    """Проверяет, есть ли активный голосовой профиль у пользователя.

    **Ответ:**
    ```json
    {
        "has_profile": true,
        "verification_enabled": false,
        "user_id": "default"
    }
    ```
    """
    db_path = settings.STORAGE_PATH / "reflexio.db"

    try:
        from src.speaker.storage import has_active_profile

        has_profile = has_active_profile(db_path, user_id)
        return {
            "has_profile": has_profile,
            "verification_enabled": settings.SPEAKER_VERIFICATION_ENABLED,
            "user_id": user_id,
            "message": (
                "Profile exists. Enable with SPEAKER_VERIFICATION_ENABLED=true in .env"
                if has_profile
                else "No profile. Create one: POST /voice/enroll with 3+ WAV samples"
            ),
        }
    except Exception as e:
        logger.error("enrollment_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Status check failed")
