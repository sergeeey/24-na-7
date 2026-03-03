"""
Сохранение транскрипций из WebSocket в SQLite (ingest_queue + transcriptions).
Схема совместима с DigestGenerator.get_transcriptions().
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.storage.db import get_reflexio_db

try:
    from src.utils.logging import get_logger
except Exception:
    import logging

    def get_logger(x):  # noqa: A001
        return logging.getLogger(x)

logger = get_logger("storage.ingest_persist")


def _ensure_sqlite_ingest_tables(conn: sqlite3.Connection) -> None:
    """Создаёт таблицы ingest_queue и transcriptions в SQLite при отсутствии."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_queue (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT,
            processed_at TEXT,
            error_message TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transcriptions (
            id TEXT PRIMARY KEY,
            ingest_id TEXT NOT NULL,
            text TEXT NOT NULL,
            language TEXT,
            language_probability REAL,
            duration REAL,
            segments TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()


def _ensure_recording_analyses_table(conn: sqlite3.Connection) -> None:
    """Создаёт таблицу recording_analyses в SQLite при отсутствии."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recording_analyses (
            id TEXT PRIMARY KEY,
            transcription_id TEXT NOT NULL,
            summary TEXT,
            emotions TEXT,
            actions TEXT,
            topics TEXT,
            urgency TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()


def save_recording_analysis(
    db_path: Path,
    transcription_id: str,
    summary: str,
    emotions: list,
    actions: list,
    topics: list,
    urgency: str,
) -> Optional[str]:
    """Сохраняет результат анализа в recording_analyses. Возвращает id записи или None."""
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)
    try:
        _ensure_recording_analyses_table(db.conn)
        analysis_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        import json

        with db.transaction():
            db.execute(
                """
                INSERT INTO recording_analyses (id, transcription_id, summary, emotions, actions, topics, urgency, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    transcription_id,
                    summary or "",
                    json.dumps(emotions) if emotions is not None else "[]",
                    json.dumps(actions) if actions is not None else "[]",
                    json.dumps(topics) if topics is not None else "[]",
                    urgency or "medium",
                    now,
                ),
            )
        logger.info("recording_analysis_saved", transcription_id=transcription_id, analysis_id=analysis_id)
        return analysis_id
    except Exception as e:
        logger.exception("recording_analysis_save_failed", transcription_id=transcription_id, error=str(e))
        return None


def _ensure_structured_events_table(conn: sqlite3.Connection) -> None:
    """Создаёт таблицу structured_events в SQLite при отсутствии."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS structured_events (
            id TEXT PRIMARY KEY,
            transcription_id TEXT NOT NULL,
            timestamp TEXT,
            duration_sec REAL DEFAULT 0.0,
            text TEXT NOT NULL,
            language TEXT DEFAULT 'unknown',
            summary TEXT DEFAULT '',
            emotions TEXT DEFAULT '[]',
            topics TEXT DEFAULT '[]',
            domains TEXT DEFAULT '[]',
            tasks TEXT DEFAULT '[]',
            decisions TEXT DEFAULT '[]',
            speakers TEXT DEFAULT '[]',
            urgency TEXT DEFAULT 'medium',
            sentiment TEXT DEFAULT 'neutral',
            location TEXT,
            asr_confidence REAL DEFAULT 0.0,
            enrichment_confidence REAL DEFAULT 0.0,
            enrichment_model TEXT DEFAULT '',
            enrichment_tokens INTEGER DEFAULT 0,
            enrichment_latency_ms REAL DEFAULT 0.0,
            created_at TEXT,
            version INTEGER DEFAULT 1,
            supersedes_id TEXT,
            is_current INTEGER DEFAULT 1
        )
        """
    )
    # ПОЧЕМУ ALTER TABLE: существующие БД не имеют новых колонок.
    # ALTER TABLE ADD COLUMN идемпотентен с try/except — безопасно вызывать повторно.
    for col_def in [
        "version INTEGER DEFAULT 1",
        "supersedes_id TEXT",
        "is_current INTEGER DEFAULT 1",
        "pitch_hz_mean REAL",
        "pitch_variance REAL",
        "energy_mean REAL",
        "spectral_centroid_mean REAL",
        "acoustic_arousal TEXT",
        "enrichment_prompt_hash TEXT",
        "enrichment_version TEXT DEFAULT ''",
    ]:
        try:
            cursor.execute(f"ALTER TABLE structured_events ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass  # колонка уже существует

    # ПОЧЕМУ partial index: запросы всегда ищут is_current=1, partial index
    # покрывает только актуальные версии — меньше размер, быстрее поиск.
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_structured_events_current
        ON structured_events(transcription_id) WHERE is_current = 1
        """
    )
    # VIEW для удобства — всегда показывает только актуальные версии
    cursor.execute(
        """
        CREATE VIEW IF NOT EXISTS current_events AS
        SELECT * FROM structured_events WHERE is_current = 1
        """
    )
    conn.commit()


def persist_structured_event(db_path: Path, event) -> Optional[str]:
    """Append-only сохранение StructuredEvent. Возвращает event.id или None.

    ПОЧЕМУ append-only вместо INSERT OR REPLACE:
    REPLACE уничтожает предыдущую версию — теряется история обогащений.
    Append-only: старая версия помечается is_current=0, новая вставляется
    с version+1 и supersedes_id → полная history для аудита и отката.
    """
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)
    try:
        _ensure_structured_events_table(db.conn)
        import json

        tasks_json = json.dumps(
            [t.model_dump() if hasattr(t, "model_dump") else {"text": str(t)} for t in (event.tasks or [])]
        )

        with db.transaction():
            # Ищем текущую версию для этого transcription_id
            existing = db.fetchone(
                """
                SELECT id, version FROM structured_events
                WHERE transcription_id = ? AND is_current = 1
                """,
                (event.transcription_id,),
            )

            version = 1
            supersedes_id = None
            if existing:
                version = (existing["version"] or 1) + 1
                supersedes_id = existing["id"]
                # Помечаем старую версию как неактуальную
                db.execute(
                    "UPDATE structured_events SET is_current = 0 WHERE id = ?",
                    (existing["id"],),
                )

            db.execute(
                """
                INSERT INTO structured_events (
                    id, transcription_id, timestamp, duration_sec, text, language,
                    summary, emotions, topics, domains, tasks, decisions, speakers,
                    urgency, sentiment, location,
                    asr_confidence, enrichment_confidence, enrichment_model,
                    enrichment_tokens, enrichment_latency_ms, created_at,
                    version, supersedes_id, is_current,
                    pitch_hz_mean, pitch_variance, energy_mean,
                    spectral_centroid_mean, acoustic_arousal,
                    enrichment_prompt_hash, enrichment_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.transcription_id,
                    event.timestamp.isoformat() if event.timestamp else None,
                    event.duration_sec,
                    event.text,
                    event.language,
                    event.summary,
                    json.dumps(event.emotions) if event.emotions else "[]",
                    json.dumps(event.topics) if event.topics else "[]",
                    json.dumps(getattr(event, "domains", [])) if getattr(event, "domains", None) else "[]",
                    tasks_json,
                    json.dumps(event.decisions) if event.decisions else "[]",
                    json.dumps(event.speakers) if event.speakers else "[]",
                    event.urgency,
                    event.sentiment,
                    event.location,
                    event.asr_confidence,
                    event.enrichment_confidence,
                    event.enrichment_model,
                    event.enrichment_tokens,
                    event.enrichment_latency_ms,
                    event.created_at.isoformat() if event.created_at else None,
                    version,
                    supersedes_id,
                    1,  # is_current
                    getattr(event, "pitch_hz_mean", None),
                    getattr(event, "pitch_variance", None),
                    getattr(event, "energy_mean", None),
                    getattr(event, "spectral_centroid_mean", None),
                    getattr(event, "acoustic_arousal", None),
                    getattr(event, "enrichment_prompt_hash", None),
                    getattr(event, "enrichment_version", ""),
                ),
            )
        logger.info(
            "structured_event_persisted",
            event_id=event.id,
            transcription_id=event.transcription_id,
            version=version,
        )
        return event.id
    except Exception as e:
        logger.exception("structured_event_persist_failed", event_id=getattr(event, "id", "?"), error=str(e))
        return None


def ensure_ingest_tables(db_path: Path) -> None:
    """Создаёт таблицы ingest_queue, transcriptions, structured_events при отсутствии."""
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)
    _ensure_sqlite_ingest_tables(db.conn)
    _ensure_recording_analyses_table(db.conn)
    _ensure_structured_events_table(db.conn)


def transcription_exists(db_path: Path, transcription_id: str) -> bool:
    """Проверяет, есть ли запись в transcriptions с данным id."""
    if not db_path.exists():
        return False
    db = get_reflexio_db(db_path)
    return db.fetchone("SELECT 1 FROM transcriptions WHERE id = ? LIMIT 1", (transcription_id,)) is not None


def get_enrichment_by_ingest_id(db_path: Path, file_id: str) -> Optional[dict[str, Any]]:
    """Возвращает enrichment данные из structured_events по ingest file_id."""
    if not db_path.exists():
        return None
    db = get_reflexio_db(db_path)
    try:
        row = db.fetchone(
            """
            SELECT se.summary, se.emotions, se.topics, se.domains, se.tasks,
                   se.urgency, se.sentiment, se.decisions, se.speakers,
                   se.enrichment_confidence, se.created_at
            FROM structured_events se
            JOIN transcriptions t ON se.transcription_id = t.id
            WHERE t.ingest_id = ? AND se.is_current = 1
            ORDER BY se.created_at DESC
            LIMIT 1
            """,
            (file_id,),
        )
        if not row:
            return None
        import json

        return {
            "summary": row["summary"] or "",
            "emotions": json.loads(row["emotions"]) if row["emotions"] else [],
            "topics": json.loads(row["topics"]) if row["topics"] else [],
            "domains": json.loads(row["domains"]) if row["domains"] else [],
            "tasks": json.loads(row["tasks"]) if row["tasks"] else [],
            "urgency": row["urgency"] or "medium",
            "sentiment": row["sentiment"] or "neutral",
            "decisions": json.loads(row["decisions"]) if row["decisions"] else [],
            "enrichment_confidence": row["enrichment_confidence"] or 0.0,
        }
    except Exception as e:
        logger.warning("get_enrichment_failed", file_id=file_id, error=str(e))
        return None


def persist_ws_transcription(
    db_path: Path,
    file_id: str,
    filename: str,
    file_path: str,
    file_size: int,
    result: dict[str, Any],
) -> Optional[str]:
    """Сохраняет результат транскрипции WebSocket в ingest_queue и transcriptions."""
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)
    try:
        _ensure_sqlite_ingest_tables(db.conn)

        existing_queue = db.fetchone("SELECT 1 FROM ingest_queue WHERE id = ?", (file_id,))
        with db.transaction():
            if not existing_queue:
                now = datetime.now(timezone.utc).isoformat()
                db.execute(
                    """
                    INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at, processed_at)
                    VALUES (?, ?, ?, ?, 'processed', ?, ?)
                    """,
                    (file_id, filename, file_path, file_size, now, now),
                )
            else:
                db.execute(
                    "UPDATE ingest_queue SET status='processed', processed_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), file_id),
                )

            existing = db.fetchone("SELECT id FROM transcriptions WHERE ingest_id = ? LIMIT 1", (file_id,))
            if existing:
                logger.debug("transcription_already_persisted", file_id=file_id, transcription_id=existing[0])
                return existing[0]

            transcription_id = str(uuid.uuid4())
            text = result.get("text") or ""
            language = result.get("language")
            language_probability = result.get("language_probability")
            duration = result.get("duration")
            segments = result.get("segments")

            segments_str = None
            if segments is not None:
                import json

                try:
                    segments_str = json.dumps(segments) if not isinstance(segments, str) else segments
                except (TypeError, ValueError):
                    segments_str = None

            db.execute(
                """
                INSERT INTO transcriptions (id, ingest_id, text, language, language_probability, duration, segments, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transcription_id,
                    file_id,
                    text,
                    language,
                    language_probability,
                    duration,
                    segments_str,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        logger.info("ws_transcription_persisted", file_id=file_id, transcription_id=transcription_id)
        return transcription_id
    except Exception as e:
        logger.exception("ws_transcription_persist_failed", file_id=file_id, error=str(e))
        return None
