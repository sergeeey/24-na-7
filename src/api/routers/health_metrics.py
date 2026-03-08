"""Health metrics ingestion API."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.storage.health_metrics import ensure_health_tables, list_health_metrics, save_health_metrics
from src.utils.config import settings

router = APIRouter(prefix="/health", tags=["health-metrics"])
limiter = Limiter(key_func=get_remote_address)


class HealthMetricBody(BaseModel):
    date: str
    steps: int | None = None
    avgHeartRate: int | None = None
    sleepHours: float | None = None
    stressLevel: float | None = None
    source: str = "android"


@router.post("/metrics")
@limiter.limit("30/minute")
async def ingest_health_metrics(request: Request, response: Response, body: HealthMetricBody):
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
@limiter.limit("60/minute")
async def get_health_metrics(
    request: Request,
    response: Response,
    day: str | None = Query(None, description="YYYY-MM-DD"),
    day_from: str | None = Query(None, alias="from"),
    day_to: str | None = Query(None, alias="to"),
):
    # ПОЧЕМУ ограничение 31 день: без лимита можно выгрузить ВСЕ данные одним GET.
    # Это и performance risk (тысячи строк), и information disclosure.
    if day_from and day_to:
        try:
            d_from = datetime.strptime(day_from, "%Y-%m-%d")
            d_to = datetime.strptime(day_to, "%Y-%m-%d")
            if (d_to - d_from).days > 31:
                raise HTTPException(status_code=400, detail="Date range exceeds 31 days. Use narrower range.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_health_tables(db_path)
    if day:
        data = list_health_metrics(db_path, day_from=day)
    else:
        data = list_health_metrics(db_path, day_from=day_from, day_to=day_to)
    return {"count": len(data), "items": data}
