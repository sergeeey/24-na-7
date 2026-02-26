"""
Social Graph API — управление персонами и голосовыми профилями окружения.

Endpoints:
  GET  /graph/persons                   — список всех персон
  GET  /graph/persons/{name}            — детали персоны
  GET  /graph/pending                   — ожидают подтверждения профиля
  POST /graph/approve/{name}            — подтвердить голосовой профиль
  POST /graph/reject/{name}             — отклонить голосовой профиль
  GET  /graph/stats                     — общая статистика графа

ПОЧЕМУ отдельный роутер:
  Social Graph — независимый домен. Отдельный роутер позволяет позже
  перенести на отдельный микросервис без изменения main.py.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.persongraph.accumulator import VoiceProfileAccumulator
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api.graph")
router = APIRouter(prefix="/graph", tags=["social-graph"])


# ──────────────────────────────────────────────
# Схемы ответов
# ──────────────────────────────────────────────


class PersonOut(BaseModel):
    name: str
    relationship: str
    voice_ready: bool
    sample_count: int
    first_seen: Optional[str]
    last_seen: Optional[str]
    approved_at: Optional[str]


class PendingApprovalOut(BaseModel):
    name: str
    sample_count: int
    avg_confidence: float
    first_sample: Optional[str]


class GraphStatsOut(BaseModel):
    total_persons: int
    voice_ready_count: int
    pending_approvals: int
    total_samples: int
    total_interactions: int


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _db() -> Path:
    return settings.STORAGE_PATH / "reflexio.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.get("/persons", response_model=list[PersonOut])
async def list_persons(
    relationship: Optional[str] = Query(None, description="Фильтр по типу связи"),
    voice_ready: Optional[bool] = Query(None, description="Только с готовым профилем"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Возвращает список известных персон из социального графа."""
    conn = _connect()
    try:
        conditions = []
        params: list = []

        if relationship is not None:
            conditions.append("relationship = ?")
            params.append(relationship)
        if voice_ready is not None:
            conditions.append("voice_ready = ?")
            params.append(1 if voice_ready else 0)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params += [limit, offset]

        rows = conn.execute(
            f"""
            SELECT name, relationship, voice_ready, sample_count,
                   first_seen, last_seen, approved_at
            FROM persons
            {where}
            ORDER BY last_seen DESC NULLS LAST
            LIMIT ? OFFSET ?
            """,  # nosec B608
            params,
        ).fetchall()

        return [
            PersonOut(
                name=r["name"],
                relationship=r["relationship"] or "unknown",
                voice_ready=bool(r["voice_ready"]),
                sample_count=r["sample_count"] or 0,
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                approved_at=r["approved_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/persons/{name}", response_model=PersonOut)
async def get_person(name: str):
    """Возвращает детали конкретной персоны."""
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT name, relationship, voice_ready, sample_count,
                   first_seen, last_seen, approved_at
            FROM persons WHERE name = ?
            """,
            (name,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Person '{name}' not found")
        return PersonOut(
            name=row["name"],
            relationship=row["relationship"] or "unknown",
            voice_ready=bool(row["voice_ready"]),
            sample_count=row["sample_count"] or 0,
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            approved_at=row["approved_at"],
        )
    finally:
        conn.close()


@router.get("/pending", response_model=list[PendingApprovalOut])
async def list_pending():
    """
    Возвращает персон с достаточно накопленными сэмплами,
    ожидающих подтверждения голосового профиля пользователем.
    """
    acc = VoiceProfileAccumulator(_db())
    rows = acc.get_pending_approvals()
    return [
        PendingApprovalOut(
            name=r["name"],
            sample_count=r["sample_count"] or 0,
            avg_confidence=round(float(r["avg_conf"] or 0.0), 3),
            first_sample=r.get("first_sample"),
        )
        for r in rows
    ]


@router.post("/approve/{name}")
async def approve_person_profile(name: str):
    """
    Пользователь подтверждает голосовой профиль персоны.

    После этого система будет идентифицировать этот голос в новых записях.
    Профиль действителен 365 дней (ежегодное переподтверждение).
    """
    acc = VoiceProfileAccumulator(_db())
    ok = acc.approve_profile(name)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"No pending samples for '{name}' or approval failed",
        )
    logger.info("profile_approved_via_api", person=name)
    return {"status": "approved", "person": name}


@router.post("/reject/{name}")
async def reject_person_profile(name: str):
    """
    Пользователь отклоняет голосовой профиль.

    Все накопленные сэмплы удаляются немедленно (privacy-first).
    """
    acc = VoiceProfileAccumulator(_db())
    acc.reject_profile(name)
    logger.info("profile_rejected_via_api", person=name)
    return {"status": "rejected", "person": name}


@router.get("/stats", response_model=GraphStatsOut)
async def graph_stats():
    """Общая статистика социального графа."""
    conn = _connect()
    try:
        total_persons = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        voice_ready = conn.execute(
            "SELECT COUNT(*) FROM persons WHERE voice_ready = 1"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(DISTINCT person_name) FROM person_voice_samples "
            "WHERE status = 'pending_approval'"
        ).fetchone()[0]
        total_samples = conn.execute(
            "SELECT COUNT(*) FROM person_voice_samples"
        ).fetchone()[0]
        total_interactions = conn.execute(
            "SELECT COUNT(*) FROM person_interactions"
        ).fetchone()[0]

        return GraphStatsOut(
            total_persons=total_persons,
            voice_ready_count=voice_ready,
            pending_approvals=pending,
            total_samples=total_samples,
            total_interactions=total_interactions,
        )
    finally:
        conn.close()
