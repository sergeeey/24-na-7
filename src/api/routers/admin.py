"""Administrative endpoints for destructive maintenance operations."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, model_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.digest.generator import DigestGenerator
from src.memory.truth import recheck_non_trusted_for_range, reclassify_episodes_for_range
from src.storage.ingest_persist import write_digest_cache
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


class ReclassifyRequest(BaseModel):
    mode: str = "dry_run"
    date: str | None = None
    date_from: str | None = None
    date_to: str | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if self.mode not in {"dry_run", "apply"}:
            raise ValueError("mode must be dry_run or apply")
        if self.date:
            return self
        if not (self.date_from and self.date_to):
            raise ValueError("date or date_from/date_to is required")
        return self


class RecheckRequest(BaseModel):
    mode: str = "dry_run"
    date: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    states: list[str] = ["uncertain", "quarantined"]

    @model_validator(mode="after")
    def validate_scope(self):
        if self.mode not in {"dry_run", "apply"}:
            raise ValueError("mode must be dry_run or apply")
        if self.date:
            pass
        elif not (self.date_from and self.date_to):
            raise ValueError("date or date_from/date_to is required")
        normalized = [state for state in self.states if state in {"uncertain", "quarantined", "garbage"}]
        self.states = normalized or ["uncertain", "quarantined"]
        return self


class ReclassifyResponse(BaseModel):
    status: str
    mode: str
    range_start: str
    range_end: str
    affected_days: list[str]
    proposed_state_counts: dict[str, int]
    proposed_transcription_state_counts: dict[str, int]
    affected_episodes: int
    affected_transcriptions: int
    digest_rebuilds: int
    transitions_written: int = 0


class RecheckResponse(BaseModel):
    status: str
    mode: str
    range_start: str
    range_end: str
    target_states: list[str]
    affected_days: list[str]
    proposed_state_counts: dict[str, int]
    proposed_transcription_state_counts: dict[str, int]
    affected_episodes: int
    affected_transcriptions: int
    digest_rebuilds: int
    transitions_written: int = 0


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


@router.post("/reclassify", response_model=ReclassifyResponse)
@limiter.limit("10/minute")
async def reclassify_truth_layer(request: Request, response: Response, body: ReclassifyRequest):
    """Dry-run or apply truth-layer reclassification for a day or date range."""
    start_day = body.date or body.date_from or ""
    end_day = body.date or body.date_to or start_day
    preview = reclassify_episodes_for_range(
        settings.STORAGE_PATH / "reflexio.db",
        start_day=start_day,
        end_day=end_day,
        apply_changes=body.mode == "apply",
    )

    digest_rebuilds = 0
    if body.mode == "apply":
        generator = DigestGenerator(settings.STORAGE_PATH / "reflexio.db")
        for day_key in preview["affected_days"]:
            digest = generator.get_daily_digest_json(date.fromisoformat(day_key))
            previous_digest_id = f"digest:{day_key}:{datetime.now(timezone.utc).isoformat()}"
            write_digest_cache(
                settings.STORAGE_PATH / "reflexio.db",
                day_key=day_key,
                digest_json=json.dumps(digest, ensure_ascii=False),
                status="ready",
                previous_digest_id=previous_digest_id,
                rebuild_reason="truth_reclassify",
                rebuilt_at=datetime.now(timezone.utc).isoformat(),
                changed_source_count=sum(1 for row in preview["episodes"] if row["day_key"] == day_key),
            )
            digest_rebuilds += 1

    return ReclassifyResponse(
        status="ok",
        mode=body.mode,
        range_start=start_day,
        range_end=end_day,
        affected_days=preview["affected_days"],
        proposed_state_counts=preview["state_counts"],
        proposed_transcription_state_counts=preview["transcription_state_counts"],
        affected_episodes=len(preview["episodes"]),
        affected_transcriptions=len(preview["transcriptions"]),
        digest_rebuilds=digest_rebuilds,
        transitions_written=(
            len([row for row in preview["episodes"] if row["old_state"] != row["new_state"]])
            + len([row for row in preview["transcriptions"] if row["old_state"] != row["new_state"]])
        )
        if body.mode == "apply"
        else 0,
    )


@router.post("/recheck", response_model=RecheckResponse)
@limiter.limit("10/minute")
async def recheck_truth_layer(request: Request, response: Response, body: RecheckRequest):
    """Selective second-pass for uncertain/quarantined memory units."""
    start_day = body.date or body.date_from or ""
    end_day = body.date or body.date_to or start_day
    preview = recheck_non_trusted_for_range(
        settings.STORAGE_PATH / "reflexio.db",
        start_day=start_day,
        end_day=end_day,
        apply_changes=body.mode == "apply",
        target_states=tuple(body.states),
    )

    digest_rebuilds = 0
    if body.mode == "apply":
        generator = DigestGenerator(settings.STORAGE_PATH / "reflexio.db")
        for day_key in preview["affected_days"]:
            digest = generator.get_daily_digest_json(date.fromisoformat(day_key))
            previous_digest_id = f"digest:{day_key}:{datetime.now(timezone.utc).isoformat()}"
            write_digest_cache(
                settings.STORAGE_PATH / "reflexio.db",
                day_key=day_key,
                digest_json=json.dumps(digest, ensure_ascii=False),
                status="ready",
                previous_digest_id=previous_digest_id,
                rebuild_reason="truth_recheck",
                rebuilt_at=datetime.now(timezone.utc).isoformat(),
                changed_source_count=(
                    sum(1 for row in preview["episodes"] if row["day_key"] == day_key)
                    + sum(1 for row in preview["transcriptions"] if row["day_key"] == day_key)
                ),
            )
            digest_rebuilds += 1

    return RecheckResponse(
        status="ok",
        mode=body.mode,
        range_start=start_day,
        range_end=end_day,
        target_states=body.states,
        affected_days=preview["affected_days"],
        proposed_state_counts=preview["state_counts"],
        proposed_transcription_state_counts=preview["transcription_state_counts"],
        affected_episodes=len(preview["episodes"]),
        affected_transcriptions=len(preview["transcriptions"]),
        digest_rebuilds=digest_rebuilds,
        transitions_written=(
            len([row for row in preview["episodes"] if row["old_state"] != row["new_state"]])
            + len([row for row in preview["transcriptions"] if row["old_state"] != row["new_state"]])
        )
        if body.mode == "apply"
        else 0,
    )
