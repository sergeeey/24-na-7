"""Router for ingest audit and integrity checks."""
from fastapi import APIRouter

from src.storage.integrity import get_ingest_integrity_report
from src.utils.config import settings

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/ingest/{ingest_id}")
async def audit_ingest(ingest_id: str):
    """Return integrity chain report for one ingest id."""
    if not settings.INTEGRITY_CHAIN_ENABLED:
        return {"status": "disabled", "reason": "INTEGRITY_CHAIN_ENABLED=false", "ingest_id": ingest_id}

    db_path = settings.STORAGE_PATH / "reflexio.db"
    report = get_ingest_integrity_report(db_path, ingest_id)
    return {"status": "ok", **report}
