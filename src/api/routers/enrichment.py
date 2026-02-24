"""Роутер для получения enrichment данных по записям.

ПОЧЕМУ отдельный роутер: enrichment — это отдельный домен от ingest/asr.
Android запрашивает enrichment ПОСЛЕ получения транскрипции (async gap ~1-5с).
"""
from fastapi import APIRouter, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.utils.config import settings
from src.utils.logging import get_logger
from src.storage.ingest_persist import get_enrichment_by_ingest_id

logger = get_logger("api.enrichment")
router = APIRouter(prefix="/enrichment", tags=["enrichment"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/by-ingest/{file_id}")
async def get_enrichment(file_id: str, request: Request, response: Response):
    """
    Возвращает enrichment данные для записи по ingest file_id.

    Android отправляет аудио через WebSocket, получает file_id.
    Через ~3-5 секунд enrichment готов — Android запрашивает его здесь.

    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/enrichment/by-ingest/550e8400-e29b-41d4-a716-446655440000"
    ```

    **Пример ответа (200):**
    ```json
    {
        "status": "enriched",
        "file_id": "550e8400-...",
        "data": {
            "summary": "Обсуждение задач на неделю",
            "emotions": ["уверенность", "спокойствие"],
            "topics": ["работа", "планирование"],
            "tasks": [{"text": "позвонить клиенту", "priority": "high"}],
            "urgency": "medium",
            "sentiment": "neutral"
        }
    }
    ```

    **Если enrichment ещё не готов (404):**
    ```json
    {
        "status": "pending",
        "file_id": "550e8400-...",
        "message": "Enrichment not ready yet"
    }
    ```
    """
    db_path = settings.STORAGE_PATH / "reflexio.db"
    result = get_enrichment_by_ingest_id(db_path, file_id)

    if result is None:
        response.status_code = 404
        return {
            "status": "pending",
            "file_id": file_id,
            "message": "Enrichment not ready yet",
        }

    return {
        "status": "enriched",
        "file_id": file_id,
        "data": result,
    }
