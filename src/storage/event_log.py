"""
Unified Event Log — наблюдательный слой поверх существующих таблиц.

ПОЧЕМУ не заменяем ingest_queue/structured_events/integrity_events:
  Слишком много кода зависит от этих таблиц — риск высокий.
  event_log — дополнительная таблица только для наблюдаемости.
  Для дебага: 1 SELECT вместо 3 JOIN через 3 таблицы.

Стадии lifecycle одного аудио-файла:
  AUDIO_RECEIVED → ASR_DONE → ENRICHED → DIGEST_COMPUTED
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.utils.logging import get_logger

logger = get_logger("storage.event_log")

STAGE_AUDIO_RECEIVED = "AUDIO_RECEIVED"
STAGE_ASR_DONE = "ASR_DONE"
STAGE_ENRICHED = "ENRICHED"
STAGE_DIGEST_COMPUTED = "DIGEST_COMPUTED"

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"


def ensure_event_log_table(db: Any) -> None:
    """Создаёт таблицу event_log (идемпотентно)."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS event_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL,
            stage       TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'ok',
            latency_ms  INTEGER,
            details     TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_session ON event_log(session_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_stage ON event_log(stage, status)"
    )
    db.conn.commit()


def log_event(
    session_id: str,
    stage: str,
    *,
    status: str = STATUS_OK,
    latency_ms: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Записывает шаг lifecycle в event_log.

    ПОЧЕМУ fire-and-forget: лог не должен ломать основной pipeline.
    При ошибке записи — только warning, данные уже сохранены в основных таблицах.

    Args:
        session_id: ID из ingest_queue (связь с основными таблицами)
        stage: одна из констант STAGE_*
        status: 'ok' | 'error' | 'skipped'
        latency_ms: время выполнения стадии в мс
        details: любые доп данные (tokens, words_count, error_message)
    """
    try:
        from src.storage.db import get_reflexio_db
        db = get_reflexio_db()
        ensure_event_log_table(db)
        db.execute(
            """
            INSERT INTO event_log (session_id, stage, status, latency_ms, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                stage,
                status,
                latency_ms,
                json.dumps(details, ensure_ascii=False) if details else None,
            ),
        )
        db.conn.commit()
    except Exception as e:
        logger.warning("event_log_write_failed", session_id=session_id, stage=stage, error=str(e))


def get_trace(session_id: str) -> List[Dict[str, Any]]:
    """
    Возвращает полный lifecycle одного session_id.

    Пример: get_trace("abc-123") →
      AUDIO_RECEIVED ok 0ms
      ASR_DONE       ok 2100ms {words: 47}
      ENRICHED       ok 1300ms {tokens: 453, model: haiku}
    """
    try:
        from src.storage.db import get_reflexio_db
        db = get_reflexio_db()
        rows = db.fetchall(
            "SELECT stage, status, latency_ms, details, created_at FROM event_log "
            "WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        result = []
        for row in rows:
            details = None
            if row[3]:
                try:
                    details = json.loads(row[3])
                except Exception:
                    details = row[3]
            result.append({
                "stage": row[0],
                "status": row[1],
                "latency_ms": row[2],
                "details": details,
                "created_at": row[4],
            })
        return result
    except Exception as e:
        logger.warning("event_log_trace_failed", session_id=session_id, error=str(e))
        return []


def get_recent_errors(limit: int = 50) -> List[Dict[str, Any]]:
    """Последние ошибки по всем стадиям — для мониторинга."""
    try:
        from src.storage.db import get_reflexio_db
        db = get_reflexio_db()
        rows = db.fetchall(
            "SELECT session_id, stage, latency_ms, details, created_at FROM event_log "
            "WHERE status = 'error' ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        result = []
        for row in rows:
            details = None
            if row[3]:
                try:
                    details = json.loads(row[3])
                except Exception:
                    details = row[3]
            result.append({
                "session_id": row[0],
                "stage": row[1],
                "latency_ms": row[2],
                "details": details,
                "created_at": row[4],
            })
        return result
    except Exception as e:
        logger.warning("event_log_errors_failed", error=str(e))
        return []
