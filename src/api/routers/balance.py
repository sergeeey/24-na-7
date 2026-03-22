"""Balance wheel API."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.balance.storage import (
    ensure_balance_tables,
    get_balance_wheel,
    get_domain_configs,
    upsert_domain_config,
)
from src.core.tool_result import add_meta
from src.persongraph.service import get_day_insights
from src.utils.config import settings

router = APIRouter(prefix="/balance", tags=["balance"])
limiter = Limiter(key_func=get_remote_address)


class DomainConfigBody(BaseModel):
    domain: str = Field(min_length=2)
    display_name: str = Field(min_length=2)
    keywords: list[str] = Field(default_factory=list)
    color: str = "#6366f1"
    icon: str = "📌"
    is_active: bool = True


@router.get("/domains")
@limiter.limit("60/minute")
async def list_domains(request: Request, response: Response):
    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_balance_tables(db_path)
    return {"domains": get_domain_configs(db_path)}


@router.post("/domains")
@limiter.limit("10/minute")
async def create_or_update_domain(request: Request, response: Response, body: DomainConfigBody):
    db_path = settings.STORAGE_PATH / "reflexio.db"
    upsert_domain_config(
        db_path=db_path,
        domain=body.domain.strip().lower(),
        display_name=body.display_name.strip(),
        keywords=[k.strip().lower() for k in body.keywords if k.strip()],
        color=body.color,
        icon=body.icon,
        is_active=body.is_active,
    )
    return {"status": "ok", "domain": body.domain}


@router.put("/domains/{domain}")
@limiter.limit("10/minute")
async def update_domain(request: Request, response: Response, domain: str, body: DomainConfigBody):
    db_path = settings.STORAGE_PATH / "reflexio.db"
    upsert_domain_config(
        db_path=db_path,
        domain=domain.strip().lower(),
        display_name=body.display_name.strip(),
        keywords=[k.strip().lower() for k in body.keywords if k.strip()],
        color=body.color,
        icon=body.icon,
        is_active=body.is_active,
    )
    return {"status": "ok", "domain": domain}


@router.get("/wheel")
@limiter.limit("30/minute")
async def wheel(
    request: Request,
    response: Response,
    date_str: str | None = Query(None, alias="date"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
):
    try:
        if date_str:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            f, t = d, d
        else:
            f = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else date.today()
            t = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else f
    except ValueError:
        raise HTTPException(status_code=400, detail="Use YYYY-MM-DD")

    db_path = settings.STORAGE_PATH / "reflexio.db"
    result = get_balance_wheel(db_path, f, t)
    evidence_count = len(result.get("domains", []))
    return add_meta(
        result,
        confidence=0.75 if evidence_count > 0 else 0.0,
        evidence_count=evidence_count,
        tool="balance_wheel",
    )


@router.get("/insights")
@limiter.limit("30/minute")
async def balance_insights(
    request: Request, response: Response, day: str = Query(..., description="YYYY-MM-DD")
):
    db_path = settings.STORAGE_PATH / "reflexio.db"
    return {"day": day, "insights": get_day_insights(db_path, day)}


@router.get("/drift")
@limiter.limit("30/minute")
async def balance_drift(
    request: Request,
    response: Response,
    window: int = Query(7, ge=1, le=30, description="Current window in days"),
    baseline: int = Query(30, ge=7, le=90, description="Baseline window in days"),
):
    """Compare domain distribution between two time windows.

    Shows what domains grew, shrank, appeared, or disappeared.
    """
    from src.balance.calculator import calculate_comparative_drift
    from src.storage.db import get_reflexio_db

    today = date.today()
    current_from = (today - timedelta(days=window - 1)).isoformat()
    baseline_from = (today - timedelta(days=baseline - 1)).isoformat()

    db = get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")
    drift = calculate_comparative_drift(
        db,
        current_from=current_from,
        current_to=today.isoformat(),
        baseline_from=baseline_from,
        baseline_to=today.isoformat(),
        current_label=f"{window}d",
        baseline_label=f"{baseline}d",
    )

    return add_meta(
        {
            "current_window": drift.current_window,
            "baseline_window": drift.baseline_window,
            "balance_delta": drift.balance_delta,
            "signals": [
                {
                    "domain": s.domain,
                    "direction": s.direction,
                    "delta": s.delta,
                    "current": s.current_presence,
                    "baseline": s.previous_presence,
                }
                for s in drift.signals
            ],
        },
        confidence=0.7 if drift.signals else 0.0,
        evidence_count=len(drift.signals),
        tool="balance_drift",
    )
