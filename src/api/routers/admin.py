"""Administrative endpoints for destructive maintenance operations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.storage.reset import reset_all_user_data
from src.utils.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])
limiter = Limiter(key_func=get_remote_address)

RESET_CONFIRM_TOKEN = "RESET_ALL_DATA"


class ResetAllRequest(BaseModel):
    confirm: str


class ResetAllResponse(BaseModel):
    status: str
    reset_at: str
    deleted_rows: dict[str, int]
    deleted_digest_files: int
    deleted_upload_files: int
    deleted_graph_projection: bool


@router.post("/reset-all", response_model=ResetAllResponse)
@limiter.limit("10/minute")
async def reset_all(request: Request, response: Response, body: ResetAllRequest):
    """Wipe all user-generated memory artifacts while preserving schema."""
    if body.confirm != RESET_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail="Explicit confirmation required: RESET_ALL_DATA",
        )

    report = reset_all_user_data(settings.STORAGE_PATH)
    return ResetAllResponse(
        status="reset",
        reset_at=report.reset_at,
        deleted_rows=report.deleted_rows,
        deleted_digest_files=report.deleted_digest_files,
        deleted_upload_files=report.deleted_upload_files,
        deleted_graph_projection=report.deleted_graph_projection,
    )
