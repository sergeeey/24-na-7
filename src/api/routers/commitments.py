"""API для обязательств и обещаний (Commitment Extraction).

ПОЧЕМУ отдельный роутер: commitments — это Relationship Guardian слой,
не просто ещё одно поле в events. Отдельный endpoint позволяет:
- фильтровать по person (кому обещал)
- агрегировать невыполненные обещания
- строить People Knowledge Base
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query

from src.utils.logging import get_logger

logger = get_logger("api.commitments")
router = APIRouter(prefix="/commitments", tags=["commitments"])


def _get_db():
    """Получить подключение к БД."""
    from src.utils.config import settings
    from src.storage.db import get_reflexio_db

    return get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")


@router.get("")
def get_commitments(
    person: Optional[str] = Query(None, description="Фильтр по имени человека"),
    days_back: int = Query(30, description="За сколько дней (по умолчанию 30)"),
    limit: int = Query(50, description="Максимум записей"),
):
    """Возвращает все обязательства/обещания за период.

    Пример: GET /commitments?person=мама&days_back=7
    """
    db = _get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    rows = db.fetchall(
        """
        SELECT id, created_at, summary, commitments, topics
        FROM structured_events
        WHERE is_current = 1
          AND commitments IS NOT NULL
          AND commitments != '[]'
          AND created_at >= ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (since, limit * 3),  # берём больше, фильтруем в Python
    )

    result = []
    for row in rows:
        try:
            raw = json.loads(row["commitments"] or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        if not raw:
            continue

        event_time = row["created_at"]
        event_id = row["id"]
        summary = row["summary"] or ""

        for c in raw:
            if not isinstance(c, dict):
                continue
            c_person = c.get("person", "")
            # Фильтр по person (case-insensitive partial match)
            if person and person.lower() not in c_person.lower():
                continue
            result.append(
                {
                    "event_id": event_id,
                    "timestamp": event_time,
                    "person": c_person,
                    "action": c.get("action", ""),
                    "deadline": c.get("deadline"),
                    "context": c.get("context"),
                    "event_summary": summary,
                }
            )
            if len(result) >= limit:
                break
        if len(result) >= limit:
            break

    # Агрегация по person
    people_stats: dict[str, int] = {}
    for c in result:
        p = c["person"]
        people_stats[p] = people_stats.get(p, 0) + 1

    return {
        "commitments": result,
        "total": len(result),
        "days_back": days_back,
        "people": people_stats,
    }


@router.get("/people")
def get_commitment_people(
    days_back: int = Query(30, description="За сколько дней"),
):
    """Список людей, которым давались обещания, с количеством.

    ПОЧЕМУ: это основа People Knowledge Base — показывает
    кому ты чаще всего обещаешь и сколько обещаний накопилось.
    """
    db = _get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    rows = db.fetchall(
        """
        SELECT commitments FROM structured_events
        WHERE is_current = 1
          AND commitments IS NOT NULL
          AND commitments != '[]'
          AND created_at >= ?
        """,
        (since,),
    )

    people: dict[str, dict] = {}
    for row in rows:
        try:
            raw = json.loads(row["commitments"] or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        for c in raw:
            if not isinstance(c, dict):
                continue
            p = c.get("person", "неизвестно")
            if p not in people:
                people[p] = {"count": 0, "actions": []}
            people[p]["count"] += 1
            action = c.get("action", "")
            if action and len(people[p]["actions"]) < 5:
                people[p]["actions"].append(action)

    # Сортировка по количеству обещаний (кому больше всего)
    sorted_people = sorted(people.items(), key=lambda x: x[1]["count"], reverse=True)

    return {
        "people": [
            {"person": name, "commitment_count": data["count"], "recent_actions": data["actions"]}
            for name, data in sorted_people
        ],
        "total_people": len(sorted_people),
        "days_back": days_back,
    }
