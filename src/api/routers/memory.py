"""Router for semantic memory retrieval."""
from fastapi import APIRouter, Query

from src.memory.semantic_memory import record_retrieval_trace, retrieve_memory
from src.utils.config import settings

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/retrieve")
async def memory_retrieve(q: str = Query(..., min_length=1), top_k: int = Query(5, ge=1, le=20)):
    """Retrieve evidence-backed memories from semantic store."""
    if not settings.RETRIEVAL_ENABLED:
        return {"status": "disabled", "reason": "RETRIEVAL_ENABLED=false", "query": q, "matches": []}

    db_path = settings.STORAGE_PATH / "reflexio.db"
    matches = retrieve_memory(db_path=db_path, query=q, top_k=top_k)
    trace_id = record_retrieval_trace(db_path=db_path, query=q, node_ids=[m["node_id"] for m in matches], top_k=top_k)
    return {
        "status": "ok",
        "query": q,
        "top_k": top_k,
        "trace_id": trace_id,
        "count": len(matches),
        "matches": matches,
    }
