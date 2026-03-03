"""Роутер для поиска по фразам."""
from fastapi import APIRouter, HTTPException, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.tool_result import add_meta
from src.utils.logging import get_logger
from src.storage.embeddings import search_phrases

logger = get_logger("api.search")
router = APIRouter(prefix="/search", tags=["search"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/events")
@limiter.limit("30/minute")
async def search_events_endpoint(request: Request, response: Response, q: str, limit: int = 10):
    """
    Семантический поиск по событиям дня через sqlite-vec (cosine similarity).

    "тревога" → находит "волнуюсь", "стресс", "беспокоюсь".
    Принципиально лучше Ctrl+F — понимает смысл, а не буквы.

    Query params:
        q: поисковый запрос
        limit: максимум результатов (default 10)
    """
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    try:
        from src.storage.db import get_reflexio_db
        from src.storage.vec_search import load_vec_extension, search_events
        db = get_reflexio_db()
        load_vec_extension(db.conn)
        results = search_events(db.conn, q, limit=limit)
        result = {"query": q, "results": results, "count": len(results)}
        return add_meta(result, confidence=0.7 if results else 0.0, evidence_count=len(results), tool="search_events")
    except Exception as e:
        logger.error("vec_search_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Search failed")


@router.post("/reindex")
@limiter.limit("2/minute")
async def reindex_endpoint(request: Request, response: Response):
    """
    Запускает retroindex — индексирует все structured_events без embedding.
    Запускать один раз после деплоя vec_search.
    """
    try:
        from src.storage.db import get_reflexio_db
        from src.storage.vec_search import ensure_vec_table, retroindex_all
        db = get_reflexio_db()
        ensure_vec_table(db.conn)
        count = retroindex_all(db.conn)
        return {"indexed": count, "status": "ok"}
    except Exception as e:
        logger.error("reindex_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Reindex failed")


@router.get("/trace/{session_id}")
@limiter.limit("60/minute")
async def get_trace_endpoint(request: Request, response: Response, session_id: str):
    """
    Полный lifecycle одного аудио-файла по session_id (= ingest_id).

    Пример: GET /search/trace/abc-123
    →  AUDIO_RECEIVED ok 0ms
       ASR_DONE       ok 2100ms {words: 47, lang: ru}
       ENRICHED       ok 1300ms {model: haiku, tokens: 453}
    """
    from src.storage.event_log import get_trace
    return {"session_id": session_id, "trace": get_trace(session_id)}


@router.get("/errors")
@limiter.limit("30/minute")
async def get_recent_errors_endpoint(request: Request, response: Response, limit: int = 50):
    """Последние N ошибок по всем стадиям pipeline — для мониторинга."""
    from src.storage.event_log import get_recent_errors
    return {"errors": get_recent_errors(limit), "count": limit}


@router.post("/phrases")
@limiter.limit("30/minute")
async def search_phrases_endpoint(request: Request, response: Response):
    """
    Поиск по фразам через semantic search (embeddings).
    
    **Тело запроса:**
    ```json
    {
        "audio_id": "550e8400-e29b-41d4-a716-446655440000",
        "query": "текст для поиска",
        "limit": 10
    }
    ```
    
    **Пример запроса:**
    ```bash
    curl -X POST "http://localhost:8000/search/phrases" \\
         -H "Content-Type: application/json" \\
         -d '{"query": "важная фраза", "limit": 10}'
    ```
    
    **Пример ответа:**
    ```json
    {
        "query": "важная фраза",
        "audio_id": null,
        "matches": [
            {
                "text": "найденная фраза",
                "similarity": 0.95,
                "timestamp": "12:34:56"
            }
        ],
        "count": 1
    }
    ```
    
    **Ошибки:**
    - `400`: query обязателен
    - `500`: Ошибка поиска
    """
    try:
        body = await request.json()
        audio_id = body.get("audio_id")
        query = body.get("query", "")
        limit = body.get("limit", 10)
        
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        
        results = search_phrases(query, audio_id=audio_id, limit=limit)
        
        return {
            "query": query,
            "audio_id": audio_id,
            "matches": results,
            "count": len(results),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("phrase_search_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Search failed. Check server logs.")
