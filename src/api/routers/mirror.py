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

# WHY: media/TV topics leak into trusted events when speaker verification
# can't distinguish TV audio played through speakers from user speech.
# Filter these from Mirror aggregation to keep the mirror clean.
_MEDIA_TOPIC_BLACKLIST = frozenset(
    {
        "канал",
        "субтитры",
        "подписка",
        "лайки",
        "подпишитесь",
        "просмотры",
        "спасибо за просмотр",
        "музыка",
        "фрагмент",
        "текст",
        "говорящий",
        "содержит",
        "выражает",
        "описание",
        "высказывание",
        # YouTube creators and shows that leak through
        "dimatorzok",
        "DimaTorzok",
        # Generic media terms
        "сезон",
        "серия",
        "эпизод",
        "трейлер",
        "реклама",
        "промо",
        "ролик",
        "видео",
        "стрим",
    }
)


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
                  AND quality_state = 'trusted'
                  AND date(created_at) BETWEEN ? AND ?
                """,
                (date_from.isoformat(), date_to.isoformat()),
            ).fetchall()

            episodes_count = len(rows)
            sentiment_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
            for row in rows:
                emotions.update(_parse_json_column(row["emotions"]))
                raw_topics = _parse_json_column(row["topics"])
                topics.update(t for t in raw_topics if t.lower() not in _MEDIA_TOPIC_BLACKLIST)
                people.update(_parse_json_column(row["speakers"]))
                sent = row["sentiment"]
                if sent and sent in sentiment_map:
                    sentiment_sum += sentiment_map[sent]
                    sentiment_count += 1
        else:
            logger.info("mirror.table_missing", table="structured_events")

        # WHY: balance_scores table doesn't exist — balance is computed on-the-fly
        # from structured_events.domains (JSON array). Extract domain mentions
        # and calculate avg sentiment per domain, same logic as /balance/wheel.
        if _table_exists(conn, "structured_events"):
            try:
                domain_rows = conn.execute(
                    """
                    SELECT domains, sentiment
                    FROM structured_events
                    WHERE is_current = 1
                      AND quality_state = 'trusted'
                      AND date(created_at) BETWEEN ? AND ?
                    """,
                    (date_from.isoformat(), date_to.isoformat()),
                ).fetchall()
                domain_counts: Counter = Counter()
                domain_sentiment: dict[str, list[float]] = {}
                for dr in domain_rows:
                    doms = _parse_json_column(dr["domains"])
                    sent_val = sentiment_map.get(dr["sentiment"], 0.0)
                    for d in doms:
                        domain_counts[d] += 1
                        domain_sentiment.setdefault(d, []).append(sent_val)
                max_mentions = max(domain_counts.values()) if domain_counts else 1
                balance_trend = [
                    {
                        "domain": d,
                        "avg_score": round(cnt / max_mentions, 2),
                        "mentions": cnt,
                    }
                    for d, cnt in domain_counts.most_common()
                ]
            except Exception as e:
                logger.warning("mirror.balance_calc_failed", error=str(e))

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

        # WHY: speakers field in structured_events is often empty because LLM
        # can't extract names from short phrases. Fall back to person_interactions
        # which tracks people via text matching on known_people names.
        if not people and _table_exists(conn, "person_interactions"):
            try:
                pi_rows = conn.execute(
                    """
                    SELECT person_name, COUNT(*) as cnt
                    FROM person_interactions
                    WHERE date(created_at) BETWEEN ? AND ?
                    GROUP BY person_name ORDER BY cnt DESC LIMIT ?
                    """,
                    (date_from.isoformat(), date_to.isoformat(), _TOP_N),
                ).fetchall()
                for r in pi_rows:
                    people[r["person_name"]] = r["cnt"]
            except Exception:
                pass
        # Also try known_people if still empty — but filter by date range
        # WHY date filter: without it, known_people returns ALL ever-mentioned people
        # even for a 1-day portrait, showing stale contacts (e.g. colleague from 3 days ago).
        if not people and _table_exists(conn, "known_people"):
            try:
                kp_rows = conn.execute(
                    "SELECT name, mention_count FROM known_people "
                    "WHERE mention_count > 0 AND date(last_mentioned_at) BETWEEN ? AND ? "
                    "ORDER BY mention_count DESC LIMIT ?",
                    (date_from.isoformat(), date_to.isoformat(), _TOP_N),
                ).fetchall()
                for r in kp_rows:
                    people[r["name"]] = r["mention_count"]
            except Exception:
                pass

    finally:
        pass  # ПОЧЕМУ не close(): get_reflexio_db() возвращает shared connection

    avg_sentiment: float | None = (
        round(sentiment_sum / sentiment_count, 4) if sentiment_count > 0 else None
    )

    # WHY: Memory Backbone — ownership breakdown for honest data quality reporting.
    ownership_breakdown = {"self": 0, "other_person": 0, "unknown": 0}
    total_events = 0
    trusted_count = 0
    if _table_exists(conn, "structured_events"):
        try:
            own_rows = conn.execute(
                """
                SELECT owner_scope, COUNT(*) as cnt
                FROM structured_events
                WHERE is_current = 1 AND date(created_at) BETWEEN ? AND ?
                GROUP BY owner_scope
                """,
                (date_from.isoformat(), date_to.isoformat()),
            ).fetchall()
            for r in own_rows:
                scope = r["owner_scope"] or "unknown"
                if scope in ownership_breakdown:
                    ownership_breakdown[scope] = r["cnt"]
                total_events += r["cnt"]
        except Exception:
            pass  # owner_scope column may not exist yet
        try:
            t_row = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM structured_events
                WHERE is_current = 1 AND quality_state = 'trusted'
                  AND date(created_at) BETWEEN ? AND ?
                """,
                (date_from.isoformat(), date_to.isoformat()),
            ).fetchone()
            trusted_count = t_row["cnt"] if t_row else 0
        except Exception:
            pass

    return {
        "emotions": emotions,
        "topics": topics,
        "people": people,
        "avg_sentiment": avg_sentiment,
        "episodes_count": episodes_count,
        "balance_trend": balance_trend,
        "open_commitments": open_commitments,
        "ownership_breakdown": ownership_breakdown,
        "data_quality": {
            "total_events": total_events,
            "trusted_count": trusted_count,
            "trusted_fraction": round(trusted_count / total_events, 3) if total_events else 0.0,
        },
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

    top_emotions = [{"emotion": e, "count": c} for e, c in agg["emotions"].most_common(_TOP_N)]
    top_topics = [{"topic": t, "count": c} for t, c in agg["topics"].most_common(_TOP_N)]
    top_people = [{"person": p, "count": c} for p, c in agg["people"].most_common(_TOP_N)]

    # WHY 5 canonical sections: Mirror v1 answers 5 questions about the user.
    # This is the first real "digital mirror" payload, not just analytics widgets.
    result: dict[str, Any] = {
        "days_back": days_back,
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        # Section 1: Who am I right now
        "identity": {
            "top_emotions": top_emotions,
            "avg_sentiment": agg["avg_sentiment"],
            "top_topics": top_topics,
            "episodes_count": episodes_count,
        },
        # Section 2: What influences me
        "influences": {
            "top_people": top_people,
            "balance_trend": agg["balance_trend"],
        },
        # Section 3: What repeats
        "patterns": {
            "open_commitments": agg["open_commitments"],
        },
        # Section 4: What's changing (placeholder — needs historical comparison)
        "drift": {},
        # Section 5: Why the system thinks so
        "evidence": {
            "ownership_breakdown": agg.get("ownership_breakdown", {}),
            "data_quality": agg.get("data_quality", {}),
        },
        # Backward compat — flat fields for existing Android UI
        "top_emotions": top_emotions,
        "top_topics": top_topics,
        "top_people": top_people,
        "avg_sentiment": agg["avg_sentiment"],
        "episodes_count": episodes_count,
        "balance_trend": agg["balance_trend"],
        "open_commitments": agg["open_commitments"],
        "ownership_breakdown": agg.get("ownership_breakdown", {}),
        "data_quality": agg.get("data_quality", {}),
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


# ── Memory Observability ──────────────────────────────────────────────────


@router.get("/memory-quality")
@limiter.limit("30/minute")
async def get_memory_quality(request: Request, response: Response) -> dict[str, Any]:
    """Memory Backbone quality dashboard — ownership, quality, invariants.

    Returns honest runtime metrics for memory health monitoring.
    Not a product endpoint — an operational diagnostics tool.
    """
    from src.memory.truth_cascade import verify_no_nulls
    from src.utils.config import settings

    db = get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")
    conn = db.conn

    # Quality summary per entity type
    def _quality_summary(table: str, where: str = "") -> dict:
        clause = f"WHERE {where}" if where else ""
        rows = conn.execute(
            f"SELECT quality_state, COUNT(*) as cnt FROM {table} {clause} "
            f"GROUP BY quality_state ORDER BY quality_state"
        ).fetchall()
        total = sum(r["cnt"] for r in rows)
        return {
            "total": total,
            "breakdown": {r["quality_state"] or "NULL": r["cnt"] for r in rows},
            "trusted_fraction": round(
                sum(r["cnt"] for r in rows if r["quality_state"] == "trusted") / total, 3
            )
            if total
            else 0.0,
        }

    # Ownership summary
    own_rows = conn.execute(
        "SELECT owner_scope, COUNT(*) as cnt FROM structured_events "
        "WHERE is_current = 1 GROUP BY owner_scope"
    ).fetchall()
    ownership = {(r["owner_scope"] or "NULL"): r["cnt"] for r in own_rows}

    # Null invariant check
    nulls = verify_no_nulls(db)

    # Lineage coverage
    try:
        lineage_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM structured_events "
            "WHERE is_current = 1 AND lineage_id IS NOT NULL"
        ).fetchone()
        lineage_total = conn.execute(
            "SELECT COUNT(*) as cnt FROM structured_events WHERE is_current = 1"
        ).fetchone()
        lineage_coverage = (
            round(lineage_row["cnt"] / lineage_total["cnt"], 3) if lineage_total["cnt"] else 0.0
        )
    except Exception:
        lineage_coverage = 0.0

    # WHY: fresh SLO separates current health from historical debt.
    # Old uncertain data from pre-speaker-verification era drags corpus SLO down,
    # but fresh events are already much healthier. Soak test needs fresh metrics.
    fresh_slo = {}
    try:
        for window, label in [("24 hours", "24h"), ("7 days", "7d")]:
            fresh = conn.execute(
                f"SELECT quality_state, owner_scope, COUNT(*) as cnt "
                f"FROM structured_events "
                f"WHERE is_current = 1 AND created_at >= datetime('now', '-{window}') "
                f"GROUP BY quality_state, owner_scope"
            ).fetchall()
            total = sum(r["cnt"] for r in fresh)
            trusted = sum(r["cnt"] for r in fresh if r["quality_state"] == "trusted")
            self_count = sum(r["cnt"] for r in fresh if r["owner_scope"] == "self")
            fresh_slo[label] = {
                "total": total,
                "trusted": trusted,
                "trusted_fraction": round(trusted / total, 3) if total else 0.0,
                "self_count": self_count,
                "self_fraction": round(self_count / total, 3) if total else 0.0,
            }
    except Exception:
        pass

    return {
        "structured_events": _quality_summary("structured_events", "is_current = 1"),
        "episodes": _quality_summary("episodes"),
        "transcriptions": _quality_summary("transcriptions"),
        "ownership": ownership,
        "invariants": {
            "null_quality_state": nulls["null_quality_state"],
            "null_owner_scope": nulls["null_owner_scope"],
            "null_lineage_id": nulls["null_lineage_id"],
            "invariant_ok": all(v == 0 for v in nulls.values()),
        },
        "lineage_coverage": lineage_coverage,
        "fresh_slo": fresh_slo,
    }
