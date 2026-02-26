"""Health metrics ingestion API."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.storage.health_metrics import ensure_health_tables, list_health_metrics, save_health_metrics
from src.utils.config import settings

router = APIRouter(prefix="/health", tags=["health-metrics"])


class HealthMetricBody(BaseModel):
    date: str
    steps: int | None = None
    avgHeartRate: int | None = None
    sleepHours: float | None = None
    stressLevel: float | None = None
    source: str = "android"


@router.post("/metrics")
async def ingest_health_metrics(body: HealthMetricBody):
    try:
        datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_health_tables(db_path)
    save_health_metrics(
        db_path=db_path,
        day=body.date,
        steps=body.steps,
        avg_heart_rate=body.avgHeartRate,
        sleep_hours=body.sleepHours,
        stress_level=body.stressLevel,
        source=body.source,
    )
    return {"status": "ok"}


@router.get("/metrics")
async def get_health_metrics(
    day: str | None = Query(None, description="YYYY-MM-DD"),
    day_from: str | None = Query(None, alias="from"),
    day_to: str | None = Query(None, alias="to"),
):
    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_health_tables(db_path)
    if day:
        data = list_health_metrics(db_path, day_from=day)
    else:
        data = list_health_metrics(db_path, day_from=day_from, day_to=day_to)
    return {"count": len(data), "items": data}
