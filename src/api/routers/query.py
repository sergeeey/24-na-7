"""
Query Engine — 5 унифицированных тулов, каждый возвращает ToolResult.

ПОЧЕМУ 5 вместо 15+:
  Старые роутеры возвращали сырые dict без confidence и evidence.
  Orchestrator не мог их объединить. Теперь все тулы совместимы.

  query_events          — семантический поиск + фильтрация (READ)
  get_digest            — дайджест с lineage (READ)
  get_person_insights   — граф персоны + статистика (READ)
  add_manual_note       — добавить заметку (WRITE, audit logged)
  trigger_digest_gen    — принудительная генерация дайджеста (IRREVERSIBLE)

Все WRITE требуют ?confirm_token=... (Permission Gate, TTL 60 сек).
"""
from __future__ import annotations

from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import json

from src.core.tool_result import ToolResult, ToolTimer, UIHint
from src.core.confidence import single_confidence
from src.api.middleware.permission_gate import (
    issue_confirmation_token,
    log_write_operation,
    verify_and_consume_token,
)
from src.utils.date_utils import resolve_date_range
from src.utils.logging import get_logger


def _safe_json_list(value: Optional[str], default: Optional[list] = None) -> list:
    """Парсит JSON-массив из БД. При битых данных возвращает default ([]), не ломает запрос."""
    default = default if default is not None else []
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else default
    except json.JSONDecodeError:
        return default


logger = get_logger("api.query")
router = APIRouter(prefix="/query", tags=["query"])


# ─────────────────────────────────────────────────────────────────────────────
# 1. query_events — универсальный READ: семантический поиск + фильтры
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/events", response_model=None)
async def query_events(
    q: str = Query(..., description="Поисковый запрос (семантический)"),
    date: Optional[str] = Query(None, description="Конкретный день YYYY-MM-DD"),
    days_back: Optional[int] = Query(None, description="Последние N дней"),
    topics: Optional[str] = Query(None, description="Фильтр по темам, через запятую"),
    emotions: Optional[str] = Query(None, description="Фильтр по эмоциям, через запятую"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    include_evidence: bool = Query(False),
) -> dict:
    """
    Семантический поиск по событиям. Возвращает ToolResult с confidence.

    Алгоритм:
      1. resolve_date_range (timezone-safe)
      2. Vec search (cosine similarity)
      3. Пост-фильтрация по topics/emotions/min_confidence
      4. Расчёт confidence по количеству evidence
    """
    with ToolTimer() as timer:
        try:
            # Период
            if date:
                dr = resolve_date_range(date_str=date)
            elif days_back:
                dr = resolve_date_range(days_back=days_back)
            else:
                dr = resolve_date_range()  # сегодня

            from src.storage.db import get_reflexio_db
            from src.storage.ingest_persist import ensure_ingest_tables
            from src.storage.vec_search import load_vec_extension, search_events
            from src.utils.config import settings
            db_path = settings.STORAGE_PATH / "reflexio.db"
            ensure_ingest_tables(db_path)
            db = get_reflexio_db(db_path)
            start_iso, end_iso = dr.sql_range()

            results = _episode_search(db, q, start_iso, end_iso, limit * 2)

            if not results:
                # Семантический поиск
                try:
                    load_vec_extension(db.conn)
                    raw_results = search_events(db.conn, q, limit=limit * 2)
                except Exception:
                    # Fallback: lexical search если vec недоступен
                    raw_results = _lexical_search(db, q, limit * 2)

                # Фильтрация по дате
                results = [
                    r for r in raw_results
                    if _in_range(r.get("created_at", ""), start_iso, end_iso)
                ]

            # Фильтрация по topics
            if topics:
                topic_list = [t.strip().lower() for t in topics.split(",")]
                results = [
                    r for r in results
                    if any(t in str(r.get("topics_json", "")).lower() for t in topic_list)
                ]

            # Фильтрация по emotions
            if emotions:
                emotion_list = [e.strip().lower() for e in emotions.split(",")]
                results = [
                    r for r in results
                    if any(e in str(r.get("emotions_json", "")).lower() for e in emotion_list)
                ]

            # Fallback: за сегодня без событий — показать сырые транскрипции
            # (пока обогащение не отработало или vec недоступен)
            if not results and dr.contains_now():
                results = _transcriptions_fallback(db, start_iso, end_iso, limit)

            # Ограничиваем
            results = results[:limit]
            evidence_ids = [str(r.get("episode_id") or r.get("id", "")) for r in results]
            conf = single_confidence(len(results))

            # Evidence metadata для визуального слоя (v0.4.0)
            # ПОЧЕМУ маппинг, а не enrichment_confidence:
            #   sentiment — эмоциональная валентность события (что случилось)
            #   enrichment_confidence — насколько LLM уверена в обогащении (качество данных)
            #   Пользователь должен видеть цвет настроения, не уверенность модели.
            _sentiment_to_score = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
            evidence_metadata = []
            for r in results:
                topics_list = _safe_json_list(r.get("topics_json"), [""])
                evidence_metadata.append({
                    "id": str(r.get("episode_id") or r.get("id", "")),
                    "timestamp": r.get("created_at", ""),
                    "sentiment_score": _sentiment_to_score.get(
                        r.get("sentiment", "neutral"), 0.5
                    ),
                    "top_topic": (topics_list or [""])[0],
                })

            # UIHint: если есть задачи — ACTION_LIST, иначе TIMELINE
            any_tasks = any(
                _safe_json_list(r.get("tasks")) for r in results
            )
            ui_hint = UIHint.ACTION_LIST if any_tasks else UIHint.TIMELINE

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("query_events_failed", error=str(e))
            result = ToolResult.error_result("query_events", str(e))
            return result.to_api_dict()

    result = ToolResult(
        data={"events": results, "period": dr.label, "total": len(results)},
        evidence_ids=evidence_ids,
        confidence=conf,
        tool_name="query_events",
        db_query_ms=timer.elapsed_ms,
        ui_hint=ui_hint,
        evidence_metadata=evidence_metadata,
    )
    return result.to_api_dict(include_evidence=include_evidence)


@router.get("/threads", response_model=None)
async def query_threads(
    days_back: int = Query(30, ge=1, le=365, description="Последние N дней для continuity lines"),
    topic: Optional[str] = Query(None, description="Фильтр по теме long thread"),
    participant: Optional[str] = Query(None, description="Фильтр по участнику"),
    status: Optional[str] = Query(None, pattern="^(active|dormant|resolved)$"),
    limit: int = Query(20, ge=1, le=100),
    include_evidence: bool = Query(False),
) -> dict:
    """Trusted continuity lines across recent days."""
    with ToolTimer() as timer:
        try:
            from pathlib import Path

            from src.memory.episodes import get_long_thread_details, get_long_threads
            from src.utils.config import settings

            db_path = Path(settings.STORAGE_PATH) / "reflexio.db"
            cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days_back)
            cutoff_key = cutoff_dt.date().isoformat()

            rows = get_long_threads(db_path)
            filtered: list[dict] = []
            topic_filter = (topic or "").strip().lower()
            participant_filter = (participant or "").strip().lower()
            status_filter = (status or "").strip().lower()

            for row in rows:
                if status_filter and str(row.get("status") or "").lower() != status_filter:
                    continue
                if str(row.get("last_seen_at") or "") < cutoff_key:
                    continue

                details = get_long_thread_details(db_path, str(row["id"]))
                if not details:
                    continue

                topics = [str(v) for v in details.get("topics", []) if str(v).strip()]
                participants = [str(v) for v in details.get("participants", []) if str(v).strip()]
                if topic_filter and not any(topic_filter in value.lower() for value in topics):
                    continue
                if participant_filter and not any(participant_filter in value.lower() for value in participants):
                    continue

                day_threads = details.get("day_threads", [])
                filtered.append(
                    {
                        "long_thread_id": details["id"],
                        "thread_key": details.get("thread_key"),
                        "summary": details.get("summary", ""),
                        "continuity_score": float(details.get("continuity_score") or 0.0),
                        "first_seen_at": details.get("first_seen_at"),
                        "last_seen_at": details.get("last_seen_at"),
                        "status": details.get("status", "active"),
                        "day_count": len(day_threads),
                        "day_thread_ids": details.get("day_thread_ids", []),
                        "participants": participants,
                        "topics": topics,
                    }
                )

            filtered = filtered[:limit]
            evidence_ids = [
                day_thread_id
                for item in filtered
                for day_thread_id in item.get("day_thread_ids", [])
            ]
            conf = single_confidence(len(filtered))

        except Exception as e:
            logger.error("query_threads_failed", error=str(e))
            return ToolResult.error_result("query_threads", str(e)).to_api_dict()

    result = ToolResult(
        data={"threads": filtered, "total": len(filtered), "days_back": days_back},
        evidence_ids=evidence_ids,
        confidence=conf,
        tool_name="query_threads",
        db_query_ms=timer.elapsed_ms,
        ui_hint=UIHint.TIMELINE,
    )
    return result.to_api_dict(include_evidence=include_evidence)


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_digest — дайджест с lineage
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/digest", response_model=None)
async def get_digest(
    date: Optional[str] = Query(None, description="YYYY-MM-DD (по умолчанию сегодня)"),
    include_evidence: bool = Query(False),
) -> dict:
    """
    Дайджест дня с data lineage. Всегда из кеша (<1 сек).
    Confidence рассчитывается по кол-ву источников в lineage.
    """
    with ToolTimer() as timer:
        try:
            dr = resolve_date_range(date_str=date) if date else resolve_date_range()
            target_date = dr.start.strftime("%Y-%m-%d")

            from src.storage.db import get_reflexio_db
            from src.storage.ingest_persist import ensure_ingest_tables
            from src.utils.config import settings
            import json as _json

            db_path = settings.STORAGE_PATH / "reflexio.db"
            ensure_ingest_tables(db_path)
            db = get_reflexio_db(db_path)

            # Из кеша
            row = db.fetchone(
                "SELECT digest_json, status FROM digest_cache WHERE date = ?",
                (target_date,),
            )

            if not row or row["status"] != "ready":
                # Генерация на лету: кеш пуст или ещё не готов (до 18:00)
                try:
                    from pathlib import Path
                    from src.digest.generator import DigestGenerator
                    db_path = Path(settings.STORAGE_PATH) / "reflexio.db"
                    generator = DigestGenerator(db_path)
                    target_date_obj = dr.start.date()
                    digest_data = generator.get_daily_digest_json(target_date_obj)
                    if not digest_data.get("total_recordings") and not digest_data.get("summary_text"):
                        return ToolResult.empty(
                            "get_digest", f"Нет записей за {target_date}."
                        ).to_api_dict()
                    evidence_ids = []
                    conf = single_confidence(
                        digest_data.get("total_recordings", 0), base_score=0.92
                    )
                    digest_data["_lineage"] = {
                        "source_count": digest_data.get("total_recordings", 0),
                        "date": target_date,
                        "live": True,
                    }
                except Exception as live_err:
                    logger.warning("get_digest_live_failed", error=str(live_err))
                    return ToolResult.empty(
                        "get_digest", f"Нет записей за {target_date}."
                    ).to_api_dict()
            else:
                digest_data = _json.loads(row["digest_json"])
                # Lineage — source events из кеша
                sources = db.fetchall(
                    "SELECT transcription_id, ingest_id FROM digest_sources WHERE date = ?",
                    (target_date,),
                )
                evidence_ids = [s["transcription_id"] for s in sources if s["transcription_id"]]
                conf = single_confidence(len(evidence_ids), base_score=0.92)
                digest_data["_lineage"] = {
                    "source_count": len(evidence_ids),
                    "date": target_date,
                }

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("get_digest_failed", error=str(e))
            return ToolResult.error_result("get_digest", str(e)).to_api_dict()

    result = ToolResult(
        data=digest_data,
        evidence_ids=evidence_ids,
        confidence=conf,
        tool_name="get_digest",
        db_query_ms=timer.elapsed_ms,
    )
    return result.to_api_dict(include_evidence=include_evidence)


# ─────────────────────────────────────────────────────────────────────────────
# 3. get_person_insights — граф персоны + статистика
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/person/{name}", response_model=None)
async def get_person_insights(
    name: str,
    include_evidence: bool = Query(False),
) -> dict:
    """
    Инсайты по персоне: профиль, статистика взаимодействий, graph-соседи.
    Confidence = f(кол-во взаимодействий, voice_ready).
    """
    with ToolTimer() as timer:
        try:
            from src.storage.db import get_reflexio_db
            db = get_reflexio_db()

            person = db.fetchone(
                "SELECT * FROM persons WHERE name = ? COLLATE NOCASE",
                (name,),
            )
            if not person:
                return ToolResult.empty(
                    "get_person_insights", f"Person '{name}' not found"
                ).to_api_dict()

            interactions = db.fetchall(
                """
                SELECT id, topics_json, emotions_json, duration_sec, created_at
                FROM person_interactions WHERE person_name = ? COLLATE NOCASE
                ORDER BY created_at DESC LIMIT 50
                """,
                (name,),
            )
            evidence_ids = [row["id"] for row in interactions]

            # Граф-соседи (если KùzuDB доступен)
            neighbors: list[dict] = []
            try:
                from src.persongraph.kuzu_engine import get_kuzu_engine
                engine = get_kuzu_engine()
                if engine.is_available():
                    neighbors = engine.get_neighbors(name, hops=1)
            except Exception:
                pass

            # Confidence: учитываем кол-во взаимодействий и voice_ready
            voice_boost = 0.05 if dict(person).get("voice_ready") else 0.0
            conf = min(single_confidence(len(interactions)) + voice_boost, 1.0)

            data = {
                "person": dict(person),
                "interactions_count": len(interactions),
                "recent_interactions": [dict(i) for i in interactions[:10]],
                "graph_neighbors": neighbors,
            }

        except Exception as e:
            logger.error("get_person_insights_failed", name=name, error=str(e))
            return ToolResult.error_result("get_person_insights", str(e)).to_api_dict()

    result = ToolResult(
        data=data,
        evidence_ids=evidence_ids,
        confidence=conf,
        tool_name="get_person_insights",
        db_query_ms=timer.elapsed_ms,
    )
    return result.to_api_dict(include_evidence=include_evidence)


# ─────────────────────────────────────────────────────────────────────────────
# 4. add_manual_note — WRITE (audit logged, rate limited)
# ─────────────────────────────────────────────────────────────────────────────

class ManualNoteRequest(BaseModel):
    text: str
    tags: list[str] = []
    date: Optional[str] = None  # YYYY-MM-DD, по умолчанию сегодня


@router.post("/note", response_model=None)
async def add_manual_note(
    body: ManualNoteRequest,
    confirm_token: Optional[str] = Query(None),
) -> dict:
    """
    Добавить ручную заметку. Логируется в audit.

    Первый вызов → 403 с confirmation_token.
    Второй вызов с ?confirm_token=... → выполняется.
    """
    payload = body.model_dump()

    # Permission Gate
    if not confirm_token:
        return issue_confirmation_token("add_manual_note", payload)

    confirmed = verify_and_consume_token(confirm_token, "add_manual_note")
    if not confirmed:
        raise HTTPException(
            status_code=403,
            detail="Invalid or expired confirm_token. Request a new one.",
        )

    with ToolTimer() as timer:
        try:
            import uuid
            import json as _json
            from src.storage.db import get_reflexio_db

            note_id = str(uuid.uuid4())
            dr = resolve_date_range(date_str=body.date) if body.date else resolve_date_range()
            target_date = dr.start.strftime("%Y-%m-%d")

            db = get_reflexio_db()
            db.execute(
                """
                INSERT INTO event_log (session_id, stage, status, details, created_at)
                VALUES (?, 'MANUAL_NOTE', 'ok', ?, datetime('now'))
                """,
                (note_id, _json.dumps({"text": body.text, "tags": body.tags, "date": target_date})),
            )
            db.conn.commit()

            log_write_operation("add_manual_note", payload, "ok")

        except Exception as e:
            log_write_operation("add_manual_note", payload, f"error: {e}")
            return ToolResult.error_result("add_manual_note", str(e)).to_api_dict()

    result = ToolResult(
        data={"note_id": note_id, "date": target_date, "text": body.text},
        evidence_ids=[note_id],
        confidence=1.0,  # ручная запись — максимальная уверенность
        tool_name="add_manual_note",
        db_query_ms=timer.elapsed_ms,
    )
    return result.to_api_dict()


# ─────────────────────────────────────────────────────────────────────────────
# 5. trigger_digest_generation — IRREVERSIBLE
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/digest/generate", response_model=None)
async def trigger_digest_generation(
    date: Optional[str] = Query(None, description="YYYY-MM-DD (по умолчанию сегодня)"),
    confirm_token: Optional[str] = Query(None),
) -> dict:
    """
    Принудительная (пере)генерация дайджеста. IRREVERSIBLE — перезапишет кеш.

    Первый вызов → 403 с confirmation_token.
    С токеном → запускает генерацию в фоне.
    """
    dr = resolve_date_range(date_str=date) if date else resolve_date_range()
    target_date = dr.start.strftime("%Y-%m-%d")
    payload = {"date": target_date}

    if not confirm_token:
        return issue_confirmation_token("trigger_digest_generation", payload)

    confirmed = verify_and_consume_token(confirm_token, "trigger_digest_generation")
    if not confirmed:
        raise HTTPException(
            status_code=403,
            detail="Invalid or expired confirm_token.",
        )

    with ToolTimer() as timer:
        try:
            from src.digest.generator import DigestGenerator
            from src.utils.config import settings
            import asyncio

            gen = DigestGenerator(settings.STORAGE_PATH / "reflexio.db")
            # Запуск в background thread (блокирующий)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: gen.generate(target_date, force=True))
            log_write_operation("trigger_digest_generation", payload, "ok")

        except Exception as e:
            log_write_operation("trigger_digest_generation", payload, f"error: {e}")
            return ToolResult.error_result("trigger_digest_generation", str(e)).to_api_dict()

    result = ToolResult(
        data={"date": target_date, "status": "generated"},
        evidence_ids=[target_date],
        confidence=0.95,
        tool_name="trigger_digest_generation",
        db_query_ms=timer.elapsed_ms,
    )
    return result.to_api_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _in_range(ts: str, start: str, end: str) -> bool:
    """Проверить что timestamp входит в диапазон."""
    if not ts:
        return True  # нет даты → не фильтруем
    return start <= ts <= end


def _lexical_search(db, q: str, limit: int) -> list[dict]:
    """Fallback лексический поиск если vec недоступен."""
    rows = db.fetchall(
        """
        SELECT id, transcription_id, text, summary, topics_json,
               emotions_json, sentiment, tasks, created_at, enrichment_confidence
        FROM structured_events
        WHERE text LIKE ? OR summary LIKE ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (f"%{q}%", f"%{q}%", limit),
    )
    return [dict(r) for r in rows]


def _episode_search(db, q: str, start_iso: str, end_iso: str, limit: int) -> list[dict]:
    """Episode-first lexical search with transcript fallback kept separate."""
    rows = db.fetchall(
        """
        SELECT e.id, e.id AS episode_id, e.thread_key AS day_thread_id, e.long_thread_key AS long_thread_id,
               e.clean_text AS text, e.started_at AS created_at,
               topics_json, participants_json, commitments_json, summary,
               needs_review, 'neutral' AS sentiment, '[]' AS emotions_json, commitments_json AS tasks
        FROM episodes e
        WHERE started_at BETWEEN ? AND ?
          AND (
            clean_text LIKE ?
            OR raw_text LIKE ?
            OR summary LIKE ?
            OR topics_json LIKE ?
            OR participants_json LIKE ?
          )
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (
            start_iso,
            end_iso,
            f"%{q}%",
            f"%{q}%",
            f"%{q}%",
            f"%{q}%",
            f"%{q}%",
            limit,
        ),
    )
    return [dict(r) for r in rows]


def _transcriptions_fallback(db, start_iso: str, end_iso: str, limit: int) -> list[dict]:
    """
    Fallback: записи из transcriptions за период, когда structured_events пуст
    (например до обогащения или при отключённом vec). Формат как у событий.
    """
    try:
        rows = db.fetchall(
            """
            SELECT id, text, created_at
            FROM transcriptions
            WHERE created_at BETWEEN ? AND ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [
            {
                "id": r["id"],
                "episode_id": r["id"],
                "text": r["text"] or "",
                "created_at": r["created_at"] or "",
                "topics_json": "[]",
                "emotions_json": "[]",
                "sentiment": "neutral",
            }
            for r in rows
        ]
    except Exception as e:
        logger.debug("transcriptions_fallback_failed", error=str(e))
        return []
