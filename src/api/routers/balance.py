"""Balance wheel API."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.balance.storage import (
    ensure_balance_tables,
    get_balance_wheel,
    get_domain_configs,
    upsert_domain_config,
)
from src.persongraph.service import get_day_insights
from src.utils.config import settings

router = APIRouter(prefix="/balance", tags=["balance"])


class DomainConfigBody(BaseModel):
    domain: str = Field(min_length=2)
    display_name: str = Field(min_length=2)
    keywords: list[str] = Field(default_factory=list)
    color: str = "#6366f1"
    icon: str = "📌"
    is_active: bool = True


@router.get("/domains")
async def list_domains():
    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_balance_tables(db_path)
    return {"domains": get_domain_configs(db_path)}


@router.post("/domains")
async def create_or_update_domain(body: DomainConfigBody):
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
async def update_domain(domain: str, body: DomainConfigBody):
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
async def wheel(
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
    return get_balance_wheel(db_path, f, t)


@router.get("/insights")
async def balance_insights(day: str = Query(..., description="YYYY-MM-DD")):
    db_path = settings.STORAGE_PATH / "reflexio.db"
    return {"day": day, "insights": get_day_insights(db_path, day)}
