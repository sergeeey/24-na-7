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

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.persongraph.accumulator import VoiceProfileAccumulator
from src.storage.db import get_reflexio_db
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api.graph")
router = APIRouter(prefix="/graph", tags=["social-graph"])
limiter = Limiter(key_func=get_remote_address)


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


class NodeOut(BaseModel):
    name: str
    relationship: str
    voice_ready: bool


class NeighborhoodOut(BaseModel):
    center: str
    nodes: list[NodeOut]
    edges: list[dict]  # {"from": ..., "to": ..., "interaction_count": ..., "last_date": ...}
    hops: int
    source: str


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _db() -> Path:
    return settings.STORAGE_PATH / "reflexio.db"


def _connect():
    return get_reflexio_db(_db())


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
    db = _connect()
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

    rows = db.fetchall(
        f"""
        SELECT name, relationship, voice_ready, sample_count,
               first_seen, last_seen, approved_at
        FROM persons
        {where}
        ORDER BY last_seen DESC NULLS LAST
        LIMIT ? OFFSET ?
        """,  # nosec B608
        params,
    )

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


@router.get("/persons/{name}", response_model=PersonOut)
async def get_person(name: str):
    """Возвращает детали конкретной персоны."""
    db = _connect()
    row = db.fetchone(
        """
        SELECT name, relationship, voice_ready, sample_count,
               first_seen, last_seen, approved_at
        FROM persons WHERE name = ?
        """,
        (name,),
    )
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
@limiter.limit("10/minute")
async def approve_person_profile(request: Request, response: Response, name: str):
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

    # ПОЧЕМУ sync здесь: approve — момент когда персона "официальна" в графе.
    # Kuzu — read projection, нет смысла синхронизировать при каждом sample.
    try:
        from src.persongraph.kuzu_engine import get_kuzu_engine
        engine = get_kuzu_engine()
        if engine.is_available():
            engine.sync_from_sqlite(_db())
            logger.info("kuzu_synced_after_approve", person=name)
    except Exception as e:
        # Kuzu — опциональный, не блокируем основной flow
        logger.warning("kuzu_sync_after_approve_failed", person=name, error=str(e))

    logger.info("profile_approved_via_api", person=name)
    return {"status": "approved", "person": name}


@router.post("/reject/{name}")
@limiter.limit("10/minute")
async def reject_person_profile(request: Request, response: Response, name: str):
    """
    Пользователь отклоняет голосовой профиль.

    Все накопленные сэмплы удаляются немедленно (privacy-first).
    """
    acc = VoiceProfileAccumulator(_db())
    acc.reject_profile(name)
    logger.info("profile_rejected_via_api", person=name)
    return {"status": "rejected", "person": name}


@router.get("/neighborhood/{name}", response_model=NeighborhoodOut)
@limiter.limit("30/minute")
async def get_neighborhood(
    request: Request,
    response: Response,
    name: str,
    hops: int = Query(2, ge=1, le=3),
):
    """
    Граф соседей персоны: кто связан с ней через N хопов.

    Приоритет: KùzuDB (multi-hop Cypher) → fallback SQLite.
    Рёбра всегда из SQLite person_interactions (взаимодействия через пользователя).
    """
    db = _connect()
    source = "sqlite_fallback"
    nodes: list[NodeOut] = []

    # 1. Пробуем KùzuDB
    try:
        from src.persongraph.kuzu_engine import get_kuzu_engine
        engine = get_kuzu_engine()
        if engine.is_available():
            raw_neighbors = engine.get_neighbors(name, hops)
            if raw_neighbors:
                # Обогащаем voice_ready из SQLite одним запросом
                neighbor_names = [n["name"] for n in raw_neighbors]
                placeholders = ",".join("?" * len(neighbor_names))
                vr_rows = db.fetchall(
                    f"SELECT name, voice_ready FROM persons WHERE name IN ({placeholders})",  # nosec B608
                    neighbor_names,
                )
                vr_map = {r["name"]: bool(r["voice_ready"]) for r in vr_rows}
                nodes = [
                    NodeOut(
                        name=n["name"],
                        relationship=n["relationship"],
                        voice_ready=vr_map.get(n["name"], False),
                    )
                    for n in raw_neighbors
                    if n["name"] != "self"
                ]
                source = "kuzu"
    except Exception as e:
        logger.warning("kuzu_neighborhood_failed", name=name, error=str(e))

    # 2. Fallback: SQLite persons
    if not nodes:
        rows = db.fetchall(
            "SELECT name, relationship, voice_ready FROM persons "
            "WHERE name != ? ORDER BY last_seen DESC LIMIT 20",
            (name,),
        )
        nodes = [
            NodeOut(
                name=r["name"],
                relationship=r["relationship"] or "unknown",
                voice_ready=bool(r["voice_ready"]),
            )
            for r in rows
        ]

    # 3. Рёбра из person_interactions (source of truth)
    if not nodes:
        return NeighborhoodOut(center=name, nodes=[], edges=[], hops=hops, source=source)

    edges: list[dict] = []
    if nodes:
        node_names = [n.name for n in nodes]
        placeholders = ",".join("?" * len(node_names))
        edge_rows = db.fetchall(
            f"""
            SELECT person_name, COUNT(*) as cnt, MAX(created_at) as last_date
            FROM person_interactions
            WHERE person_name IN ({placeholders})
            GROUP BY person_name
            """,  # nosec B608
            node_names,
        )
        edge_map = {r["person_name"]: r for r in edge_rows}
        edges = [
            {
                "from": name,
                "to": n.name,
                "interaction_count": int(edge_map.get(n.name, {}).get("cnt", 0)),
                "last_date": (edge_map.get(n.name, {}).get("last_date", "") or "")[:10],
            }
            for n in nodes
        ]

    return NeighborhoodOut(
        center=name,
        nodes=nodes,
        edges=edges,
        hops=hops,
        source=source,
    )


@router.get("/stats", response_model=GraphStatsOut)
async def graph_stats():
    """Общая статистика социального графа."""
    db = _connect()
    total_persons = db.fetchone("SELECT COUNT(*) FROM persons")[0]
    voice_ready = db.fetchone(
        "SELECT COUNT(*) FROM persons WHERE voice_ready = 1"
    )[0]
    pending = db.fetchone(
        "SELECT COUNT(DISTINCT person_name) FROM person_voice_samples "
        "WHERE status = 'pending_approval'"
    )[0]
    total_samples = db.fetchone(
        "SELECT COUNT(*) FROM person_voice_samples"
    )[0]
    total_interactions = db.fetchone(
        "SELECT COUNT(*) FROM person_interactions"
    )[0]

    return GraphStatsOut(
        total_persons=total_persons,
        voice_ready_count=voice_ready,
        pending_approvals=pending,
        total_samples=total_samples,
        total_interactions=total_interactions,
    )
