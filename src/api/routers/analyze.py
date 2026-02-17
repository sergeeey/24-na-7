"""Роутер для анализа транскрипций."""
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from src.utils.config import settings
from src.utils.logging import get_logger
from src.storage.ingest_persist import save_recording_analysis, transcription_exists
from src.summarizer.few_shot import analyze_recording_text

logger = get_logger("api.analyze")
router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeTextBody(BaseModel):
    """Тело запроса POST /analyze/text."""
    transcription: str
    transcription_id: str | None = None
    user_context: str | None = None


@router.post("/text")
def analyze_text(body: AnalyzeTextBody = Body(...)):
    """
    Анализ смысла транскрипции: саммари, эмоции, действия, темы, срочность.
    
    Если передан transcription_id и запись есть в БД — результат сохраняется в recording_analyses.
    
    **Тело запроса:**
    ```json
    {
        "transcription": "текст для анализа",
        "transcription_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_context": "контекст пользователя (опционально)"
    }
    ```
    
    **Пример запроса:**
    ```bash
    curl -X POST "http://localhost:8000/analyze/text" \\
         -H "Content-Type: application/json" \\
         -d '{"transcription": "Сегодня я сделал много важных дел"}'
    ```
    
    **Пример ответа:**
    ```json
    {
        "summary": "Пользователь выполнил множество задач",
        "emotions": ["удовлетворение", "гордость"],
        "actions": ["выполнение задач"],
        "topics": ["продуктивность"],
        "urgency": "medium"
    }
    ```
    
    **Ошибки:**
    - `400`: transcription обязателен и не должен быть пустым
    - `500`: Ошибка анализа
    """
    if not (body.transcription or "").strip():
        raise HTTPException(status_code=400, detail="transcription is required and must be non-empty")
    try:
        analysis = analyze_recording_text(body.transcription)
    except Exception as e:
        logger.exception("analyze_text_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    db_path = settings.STORAGE_PATH / "reflexio.db"
    if body.transcription_id and transcription_exists(db_path, body.transcription_id):
        save_recording_analysis(
            db_path=db_path,
            transcription_id=body.transcription_id,
            summary=analysis.get("summary") or "",
            emotions=analysis.get("emotions") or [],
            actions=analysis.get("actions") or [],
            topics=analysis.get("topics") or [],
            urgency=analysis.get("urgency") or "medium",
        )
    return {
        "summary": analysis.get("summary"),
        "emotions": analysis.get("emotions"),
        "actions": analysis.get("actions"),
        "topics": analysis.get("topics"),
        "urgency": analysis.get("urgency"),
    }
