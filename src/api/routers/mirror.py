"""Mirror API — еженедельный портрет пользователя на основе накопленных эпизодов."""

import json
from collections import Counter
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.tool_result import add_meta
from src.storage.db import get_reflexio_db
from src.utils.logging import get_logger

logger = get_logger("api.mirror")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/mirror", tags=["mirror"])

_TOP_N = 5


# ── Pydantic-схемы ответа ──────────────────────────────────────────────────


class EmotionCount(BaseModel):
    """Эмоция и количество её упоминаний."""

    emotion: str
    count: int


class TopicCount(BaseModel):
    """Тема и количество её упоминаний."""

    topic: str
    count: int


class PersonCount(BaseModel):
    """Человек и количество его упоминаний."""

    person: str
    count: int


class DomainTrend(BaseModel):
    """Средний балл домена колеса жизни за период."""

    domain: str
    avg_score: float


class PortraitResponse(BaseModel):
    """Портрет пользователя за выбранный период."""

    days_back: int
    period: dict[str, str]
    top_emotions: list[EmotionCount]
    top_topics: list[TopicCount]
    top_people: list[PersonCount]
    avg_sentiment: float | None
    episodes_count: int
    balance_trend: list[DomainTrend]
    open_commitments: int


# ── Вспомогательные функции ────────────────────────────────────────────────


def _parse_json_column(raw: str | None) -> list[str]:
    """Безопасно разбирает JSON-колонку в список строк.

    Возвращает пустой список при NULL, пустой строке или невалидном JSON —
    LLM иногда записывает некорректный JSON в старые строки.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        # ПОЧЕМУ проверяем isinstance: колонка теоретически может содержать
        # одиночную строку вместо списка — обрабатываем оба варианта без краша.
        if isinstance(parsed, list):
            return [str(item).lower().strip() for item in parsed if item]
        return []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _table_exists(conn, table_name: str) -> bool:
    """Проверяет существование таблицы без исключений."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _query_portrait(
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    """Выполняет все SQL-запросы и возвращает сырые агрегаты.

    Читает три таблицы: enriched_episodes, balance_scores, commitments.
    При отсутствии таблицы возвращает нули по соответствующей метрике.
    """
    emotions: Counter = Counter()
    topics: Counter = Counter()
    people: Counter = Counter()
    sentiment_sum = 0.0
    sentiment_count = 0
    episodes_count = 0
    balance_trend: list[dict[str, Any]] = []
    open_commitments = 0

    # ПОЧЕМУ get_reflexio_db(): на проде БД может быть sqlcipher-зашифрована,
    # прямой sqlite3.connect() не сможет открыть файл.
    conn = get_reflexio_db()

    try:
        # --- structured_events + episodes: эмоции, темы, люди, сентимент ---
        # WHY: was enriched_episodes (legacy table that doesn't exist).
        # Now reads from structured_events (current enrichment output).
        if _table_exists(conn, "structured_events"):
            rows = conn.execute(
                """
                SELECT emotions, topics, speakers, sentiment
                FROM structured_events
                WHERE is_current = 1
                  AND date(created_at) BETWEEN ? AND ?
                """,
                (date_from.isoformat(), date_to.isoformat()),
            ).fetchall()

            episodes_count = len(rows)
            sentiment_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
            for row in rows:
                emotions.update(_parse_json_column(row["emotions"]))
                topics.update(_parse_json_column(row["topics"]))
                people.update(_parse_json_column(row["speakers"]))
                sent = row["sentiment"]
                if sent and sent in sentiment_map:
                    sentiment_sum += sentiment_map[sent]
                    sentiment_count += 1
        else:
            logger.info("mirror.table_missing", table="structured_events")

        # --- balance_scores: тренд по доменам ---
        if _table_exists(conn, "balance_scores"):
            balance_rows = conn.execute(
                """
                SELECT domain, AVG(score) AS avg_score
                FROM balance_scores
                WHERE date BETWEEN ? AND ?
                GROUP BY domain
                ORDER BY domain
                """,
                (date_from.isoformat(), date_to.isoformat()),
            ).fetchall()
            balance_trend = [
                {"domain": r["domain"], "avg_score": round(float(r["avg_score"]), 2)}
                for r in balance_rows
            ]
        else:
            logger.info("mirror.table_missing", table="balance_scores")

        # --- commitments: открытые обязательства ---
        if _table_exists(conn, "commitments"):
            # ПОЧЕМУ без фильтра по периоду: обязательства — сквозная таблица.
            # Пользователю важно видеть ВСЕ открытые пункты, а не только за N дней.
            row_c = conn.execute(
                "SELECT COUNT(*) FROM commitments"
                " WHERE deadline IS NULL OR date(deadline) >= date('now')",
            ).fetchone()
            open_commitments = int(row_c[0]) if row_c else 0
        else:
            logger.info("mirror.table_missing", table="commitments")

    finally:
        pass  # ПОЧЕМУ не close(): get_reflexio_db() возвращает shared connection

    avg_sentiment: float | None = (
        round(sentiment_sum / sentiment_count, 4) if sentiment_count > 0 else None
    )

    return {
        "emotions": emotions,
        "topics": topics,
        "people": people,
        "avg_sentiment": avg_sentiment,
        "episodes_count": episodes_count,
        "balance_trend": balance_trend,
        "open_commitments": open_commitments,
    }


# ── Endpoint ───────────────────────────────────────────────────────────────


@router.get("/portrait")
@limiter.limit("30/minute")
async def get_portrait(
    request: Request,
    response: Response,
    days_back: int = Query(7, ge=1, le=90, description="Глубина анализа в днях"),
) -> dict[str, Any]:
    """Возвращает еженедельный портрет пользователя.

    Агрегирует топ-эмоции, темы, людей, средний сентимент из enriched_episodes,
    тренд баланса из balance_scores, количество открытых обязательств из commitments.

    Args:
        days_back: период анализа в днях (1–90, default 7)
    """
    date_to = date.today()
    # ПОЧЕМУ days_back - 1: при days_back=7 включаем сегодня + 6 предыдущих = 7 дней итого.
    date_from = date_to - timedelta(days=days_back - 1)

    logger.info(
        "mirror.portrait_request",
        days_back=days_back,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
    )

    agg = _query_portrait(date_from, date_to)
    episodes_count: int = agg["episodes_count"]

    result: dict[str, Any] = {
        "days_back": days_back,
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "top_emotions": [
            {"emotion": e, "count": c} for e, c in agg["emotions"].most_common(_TOP_N)
        ],
        "top_topics": [{"topic": t, "count": c} for t, c in agg["topics"].most_common(_TOP_N)],
        "top_people": [{"person": p, "count": c} for p, c in agg["people"].most_common(_TOP_N)],
        "avg_sentiment": agg["avg_sentiment"],
        "episodes_count": episodes_count,
        "balance_trend": agg["balance_trend"],
        "open_commitments": agg["open_commitments"],
    }

    # ПОЧЕМУ такая формула confidence: при 0 эпизодов — 0.0, при ~30 — 0.9.
    # Отражает реальную статистическую надёжность агрегации.
    confidence = min(0.9, episodes_count * 0.03) if episodes_count > 0 else 0.0

    logger.info(
        "mirror.portrait_built",
        episodes_count=episodes_count,
        confidence=round(confidence, 2),
        open_commitments=agg["open_commitments"],
    )

    return add_meta(
        result, confidence=confidence, evidence_count=episodes_count, tool="mirror_portrait"
    )
