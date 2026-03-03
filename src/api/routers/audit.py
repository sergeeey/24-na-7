"""Router for ingest audit and integrity checks."""
from fastapi import APIRouter, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.storage.integrity import get_ingest_integrity_report
from src.utils.config import settings

router = APIRouter(prefix="/audit", tags=["audit"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/ingest/{ingest_id}")
@limiter.limit("60/minute")
async def audit_ingest(request: Request, response: Response, ingest_id: str):
    """Return integrity chain report for one ingest id."""
    if not settings.INTEGRITY_CHAIN_ENABLED:
        return {"status": "disabled", "reason": "INTEGRITY_CHAIN_ENABLED=false", "ingest_id": ingest_id}

    db_path = settings.STORAGE_PATH / "reflexio.db"
    report = get_ingest_integrity_report(db_path, ingest_id)
    return {"status": "ok", **report}
