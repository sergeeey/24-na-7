"""
Сохранение транскрипций из WebSocket в SQLite (ingest_queue + transcriptions).
Схема совместима с DigestGenerator.get_transcriptions().
"""

from __future__ import annotations

import sqlite3
import uuid
import json
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

QUALITY_STATES = ("trusted", "uncertain", "garbage", "quarantined")


def _ensure_sqlite_ingest_tables(conn: sqlite3.Connection) -> None:
    """Создаёт таблицы ingest_queue и transcriptions в SQLite при отсутствии."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_queue (
            id TEXT PRIMARY KEY,
            segment_id TEXT,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            transport_status TEXT NOT NULL DEFAULT 'received',
            processing_status TEXT NOT NULL DEFAULT 'received',
            captured_at TEXT,
            audio_sha256 TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT,
            error_code TEXT,
            created_at TEXT,
            processed_at TEXT,
            error_message TEXT,
            quarantine_reason TEXT,
            quality_score REAL,
            needs_recheck INTEGER NOT NULL DEFAULT 0,
            quality_state TEXT NOT NULL DEFAULT 'trusted',
            quality_reasons_json TEXT NOT NULL DEFAULT '[]',
            review_required INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    for col_def in [
        "segment_id TEXT",
        "transport_status TEXT NOT NULL DEFAULT 'received'",
        "processing_status TEXT NOT NULL DEFAULT 'received'",
        "captured_at TEXT",
        "audio_sha256 TEXT",
        "attempt_count INTEGER NOT NULL DEFAULT 0",
        "next_attempt_at TEXT",
        "error_code TEXT",
        "quarantine_reason TEXT",
        "quality_score REAL",
        "needs_recheck INTEGER NOT NULL DEFAULT 0",
        "quality_state TEXT NOT NULL DEFAULT 'trusted'",
        "quality_reasons_json TEXT NOT NULL DEFAULT '[]'",
        "review_required INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            cursor.execute(f"ALTER TABLE ingest_queue ADD COLUMN {col_def}")
        except Exception:
            pass
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ingest_queue_segment_id ON ingest_queue(segment_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ingest_queue_status ON ingest_queue(status)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transcriptions (
            id TEXT PRIMARY KEY,
            ingest_id TEXT NOT NULL,
            episode_id TEXT,
            text TEXT NOT NULL,
            transcript_raw TEXT,
            transcript_clean TEXT,
            language TEXT,
            language_probability REAL,
            asr_model TEXT,
            asr_confidence REAL,
            garbage_flag INTEGER NOT NULL DEFAULT 0,
            quality_score REAL,
            needs_recheck INTEGER NOT NULL DEFAULT 0,
            quality_state TEXT NOT NULL DEFAULT 'trusted',
            quality_reasons_json TEXT NOT NULL DEFAULT '[]',
            review_required INTEGER NOT NULL DEFAULT 0,
            duration REAL,
            segments TEXT,
            created_at TEXT
        )
        """
    )
    for col_def in [
        "transcript_raw TEXT",
        "transcript_clean TEXT",
        "episode_id TEXT",
        "asr_model TEXT",
        "asr_confidence REAL",
        "garbage_flag INTEGER NOT NULL DEFAULT 0",
        "quality_score REAL",
        "needs_recheck INTEGER NOT NULL DEFAULT 0",
        "quality_state TEXT NOT NULL DEFAULT 'trusted'",
        "quality_reasons_json TEXT NOT NULL DEFAULT '[]'",
        "review_required INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            cursor.execute(f"ALTER TABLE transcriptions ADD COLUMN {col_def}")
        except Exception:
            pass
    _ensure_digest_cache_table(conn)
    _ensure_quality_transition_table(conn)
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


def _ensure_episodes_tables(conn: sqlite3.Connection) -> None:
    """Создаёт таблицы episodes и day_threads при отсутствии."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            source_count INTEGER NOT NULL DEFAULT 0,
            transcription_ids_json TEXT NOT NULL DEFAULT '[]',
            raw_text TEXT NOT NULL DEFAULT '',
            clean_text TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            topics_json TEXT NOT NULL DEFAULT '[]',
            participants_json TEXT NOT NULL DEFAULT '[]',
            commitments_json TEXT NOT NULL DEFAULT '[]',
            importance_score REAL DEFAULT 0.0,
            needs_review INTEGER NOT NULL DEFAULT 0,
            quality_state TEXT NOT NULL DEFAULT 'trusted',
            quality_score REAL DEFAULT 1.0,
            quality_reasons_json TEXT NOT NULL DEFAULT '[]',
            review_required INTEGER NOT NULL DEFAULT 0,
            day_key TEXT NOT NULL,
            thread_key TEXT,
            long_thread_key TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS day_threads (
            id TEXT PRIMARY KEY,
            day_key TEXT NOT NULL,
            topic_cluster TEXT NOT NULL,
            episode_ids_json TEXT NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL DEFAULT '',
            open_questions TEXT NOT NULL DEFAULT '',
            commitments_json TEXT NOT NULL DEFAULT '[]',
            topics_json TEXT NOT NULL DEFAULT '[]',
            participants_json TEXT NOT NULL DEFAULT '[]',
            carryover_candidate INTEGER NOT NULL DEFAULT 0,
            long_thread_key TEXT,
            topic_overlap_score REAL NOT NULL DEFAULT 0.0,
            participant_overlap_score REAL NOT NULL DEFAULT 0.0,
            temporal_proximity_score REAL NOT NULL DEFAULT 0.0,
            commitment_overlap_score REAL NOT NULL DEFAULT 0.0,
            thread_confidence REAL NOT NULL DEFAULT 0.0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS long_threads (
            id TEXT PRIMARY KEY,
            thread_key TEXT NOT NULL UNIQUE,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            day_thread_ids_json TEXT NOT NULL DEFAULT '[]',
            participants_json TEXT NOT NULL DEFAULT '[]',
            topics_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            summary TEXT NOT NULL DEFAULT '',
            continuity_score REAL NOT NULL DEFAULT 0.0
        )
        """
    )
    for col_def in [
        "quality_state TEXT NOT NULL DEFAULT 'trusted'",
        "quality_score REAL DEFAULT 1.0",
        "quality_reasons_json TEXT NOT NULL DEFAULT '[]'",
        "review_required INTEGER NOT NULL DEFAULT 0",
        "long_thread_key TEXT",
    ]:
        try:
            cursor.execute(f"ALTER TABLE episodes ADD COLUMN {col_def}")
        except Exception:
            pass
    for col_def in [
        "topics_json TEXT NOT NULL DEFAULT '[]'",
        "participants_json TEXT NOT NULL DEFAULT '[]'",
        "long_thread_key TEXT",
        "topic_overlap_score REAL NOT NULL DEFAULT 0.0",
        "participant_overlap_score REAL NOT NULL DEFAULT 0.0",
        "temporal_proximity_score REAL NOT NULL DEFAULT 0.0",
        "commitment_overlap_score REAL NOT NULL DEFAULT 0.0",
        "thread_confidence REAL NOT NULL DEFAULT 0.0",
    ]:
        try:
            cursor.execute(f"ALTER TABLE day_threads ADD COLUMN {col_def}")
        except Exception:
            pass
    for col_def in [
        "participants_json TEXT NOT NULL DEFAULT '[]'",
        "topics_json TEXT NOT NULL DEFAULT '[]'",
        "status TEXT NOT NULL DEFAULT 'active'",
        "summary TEXT NOT NULL DEFAULT ''",
        "continuity_score REAL NOT NULL DEFAULT 0.0",
    ]:
        try:
            cursor.execute(f"ALTER TABLE long_threads ADD COLUMN {col_def}")
        except Exception:
            pass
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_day_key ON episodes(day_key, started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status, ended_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_quality_state ON episodes(quality_state, day_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_day_threads_day_key ON day_threads(day_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_day_threads_confidence ON day_threads(day_key, thread_confidence)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_day_threads_long_thread_key ON day_threads(long_thread_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_long_threads_status ON long_threads(status, last_seen_at)")
    conn.commit()


def _ensure_digest_cache_table(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS digest_cache (
            date TEXT PRIMARY KEY,
            digest_json TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready',
            previous_digest_id TEXT,
            rebuild_reason TEXT,
            rebuilt_at TEXT,
            changed_source_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    for col_def in [
        "previous_digest_id TEXT",
        "rebuild_reason TEXT",
        "rebuilt_at TEXT",
        "changed_source_count INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            cursor.execute(f"ALTER TABLE digest_cache ADD COLUMN {col_def}")
        except Exception:
            pass
    conn.commit()


def _ensure_quality_transition_table(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quality_state_transition_log (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            old_state TEXT,
            new_state TEXT NOT NULL,
            reason_codes_json TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quality_transition_entity
        ON quality_state_transition_log(entity_type, entity_id, created_at)
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
        logger.info(
            "recording_analysis_saved", transcription_id=transcription_id, analysis_id=analysis_id
        )
        return analysis_id
    except Exception as e:
        logger.exception(
            "recording_analysis_save_failed", transcription_id=transcription_id, error=str(e)
        )
        return None


def _ensure_structured_events_table(conn: sqlite3.Connection) -> None:
    """Создаёт таблицу structured_events в SQLite при отсутствии."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS structured_events (
            id TEXT PRIMARY KEY,
            transcription_id TEXT NOT NULL,
            episode_id TEXT,
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
        "episode_id TEXT",
        "pitch_hz_mean REAL",
        "pitch_variance REAL",
        "energy_mean REAL",
        "spectral_centroid_mean REAL",
        "acoustic_arousal TEXT",
        "enrichment_prompt_hash TEXT",
        "enrichment_version TEXT DEFAULT ''",
        "commitments TEXT DEFAULT '[]'",
    ]:
        try:
            cursor.execute(f"ALTER TABLE structured_events ADD COLUMN {col_def}")
        except Exception:
            pass  # колонка уже существует (sqlite3 или sqlcipher3 OperationalError)

    # ПОЧЕМУ partial index: запросы всегда ищут is_current=1, partial index
    # покрывает только актуальные версии — меньше размер, быстрее поиск.
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_structured_events_current
        ON structured_events(transcription_id) WHERE is_current = 1
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_structured_events_episode_current
        ON structured_events(episode_id) WHERE is_current = 1
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
            [
                t.model_dump() if hasattr(t, "model_dump") else {"text": str(t)}
                for t in (event.tasks or [])
            ]
        )

        with db.transaction():
            # Ищем текущую версию для этого transcription_id
            existing = db.fetchone(
                """
                SELECT id, version FROM structured_events
                WHERE (
                    (episode_id = ? AND ? IS NOT NULL)
                    OR (transcription_id = ? AND ? IS NULL)
                ) AND is_current = 1
                """,
                (
                    getattr(event, "episode_id", None),
                    getattr(event, "episode_id", None),
                    event.transcription_id,
                    getattr(event, "episode_id", None),
                ),
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
                    id, transcription_id, episode_id, timestamp, duration_sec, text, language,
                    summary, emotions, topics, domains, tasks, commitments,
                    decisions, speakers,
                    urgency, sentiment, location,
                    asr_confidence, enrichment_confidence, enrichment_model,
                    enrichment_tokens, enrichment_latency_ms, created_at,
                    version, supersedes_id, is_current,
                    pitch_hz_mean, pitch_variance, energy_mean,
                    spectral_centroid_mean, acoustic_arousal,
                    enrichment_prompt_hash, enrichment_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.transcription_id,
                    getattr(event, "episode_id", None),
                    event.timestamp.isoformat() if event.timestamp else None,
                    event.duration_sec,
                    event.text,
                    event.language,
                    event.summary,
                    json.dumps(event.emotions) if event.emotions else "[]",
                    json.dumps(event.topics) if event.topics else "[]",
                    json.dumps(getattr(event, "domains", []))
                    if getattr(event, "domains", None)
                    else "[]",
                    tasks_json,
                    json.dumps(
                        [
                            c.model_dump() if hasattr(c, "model_dump") else c
                            for c in (event.commitments or [])
                        ]
                    )
                    if event.commitments
                    else "[]",
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
        # ПОЧЕМУ async vec indexing: не блокируем pipeline если sqlite-vec недоступен.
        # Graceful — при ошибке только warning, событие уже сохранено.
        if event.text:
            try:
                from src.storage.vec_search import index_event, load_vec_extension

                load_vec_extension(db.conn)
                index_event(db.conn, event.id, event.text)
            except Exception as _ve:
                logger.warning("vec_index_skipped", event_id=event.id, error=str(_ve))
        return event.id
    except Exception as e:
        logger.exception(
            "structured_event_persist_failed", event_id=getattr(event, "id", "?"), error=str(e)
        )
        return None


def ensure_ingest_tables(db_path: Path) -> None:
    """Создаёт таблицы ingest_queue, transcriptions, structured_events при отсутствии."""
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)
    _ensure_sqlite_ingest_tables(db.conn)
    _ensure_recording_analyses_table(db.conn)
    _ensure_episodes_tables(db.conn)
    _ensure_structured_events_table(db.conn)


def write_digest_cache(
    db_path: Path,
    *,
    day_key: str,
    digest_json: str,
    status: str = "ready",
    previous_digest_id: str | None = None,
    rebuild_reason: str | None = None,
    rebuilt_at: str | None = None,
    changed_source_count: int = 0,
) -> None:
    db = get_reflexio_db(db_path)
    _ensure_digest_cache_table(db.conn)
    generated_at = datetime.now(timezone.utc).isoformat()
    with db.transaction():
        db.execute(
            """
            INSERT OR REPLACE INTO digest_cache (
                date, digest_json, generated_at, status,
                previous_digest_id, rebuild_reason, rebuilt_at, changed_source_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day_key,
                digest_json,
                generated_at,
                status,
                previous_digest_id,
                rebuild_reason,
                rebuilt_at,
                changed_source_count,
            ),
        )


def get_existing_ingest(db_path: Path, *, segment_id: str | None = None) -> Optional[sqlite3.Row]:
    """Вернуть существующий ingest row по segment_id, если он уже был принят."""
    if not segment_id:
        return None
    db = get_reflexio_db(db_path)
    _ensure_sqlite_ingest_tables(db.conn)
    return db.fetchone(
        "SELECT * FROM ingest_queue WHERE segment_id = ? ORDER BY created_at DESC LIMIT 1",
        (segment_id,),
    )


def get_transcription_by_ingest_id(db_path: Path, ingest_id: str) -> Optional[dict[str, Any]]:
    """Вернуть транскрипцию для dedupe-ответа по ingest_id."""
    if not db_path.exists():
        return None
    db = get_reflexio_db(db_path)
    _ensure_sqlite_ingest_tables(db.conn)
    row = db.fetchone(
        """
        SELECT text, transcript_clean, language, language_probability, quality_score, needs_recheck, quality_state
        FROM transcriptions
        WHERE ingest_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (ingest_id,),
    )
    if not row:
        return None
    return {
        "text": row["transcript_clean"] or row["text"] or "",
        "language": row["language"] or "",
        "language_probability": row["language_probability"],
        "quality_score": row["quality_score"],
        "needs_recheck": bool(row["needs_recheck"]),
        "quality_state": row["quality_state"] or "trusted",
    }


def transcription_exists(db_path: Path, transcription_id: str) -> bool:
    """Проверяет, есть ли запись в transcriptions с данным id."""
    if not db_path.exists():
        return False
    db = get_reflexio_db(db_path)
    return (
        db.fetchone("SELECT 1 FROM transcriptions WHERE id = ? LIMIT 1", (transcription_id,))
        is not None
    )


def get_enrichment_by_ingest_id(db_path: Path, file_id: str) -> Optional[dict[str, Any]]:
    """Возвращает enrichment данные из structured_events по ingest file_id."""
    if not db_path.exists():
        return None
    db = get_reflexio_db(db_path)
    try:
        row = db.fetchone(
            """
        SELECT se.summary, se.emotions, se.topics, se.domains, se.tasks,
                   se.urgency, se.sentiment, se.decisions, se.speakers, se.episode_id,
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
            "episode_id": row["episode_id"],
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
    if not result or not isinstance(result, dict):
        logger.warning(
            "persist_ws_transcription_invalid_result",
            file_id=file_id,
            result_type=type(result).__name__,
        )
        return None
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)
    try:
        _ensure_sqlite_ingest_tables(db.conn)
        _ensure_episodes_tables(db.conn)

        existing_queue = db.fetchone("SELECT 1 FROM ingest_queue WHERE id = ?", (file_id,))
        with db.transaction():
            if not existing_queue:
                now = datetime.now(timezone.utc).isoformat()
                db.execute(
                    """
                    INSERT INTO ingest_queue (
                        id, filename, file_path, file_size, status,
                        transport_status, processing_status, created_at, processed_at,
                        quality_score, needs_recheck
                    , quality_state, quality_reasons_json, review_required
                    )
                    VALUES (?, ?, ?, ?, 'transcribed', 'server_acked', 'transcribed', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        filename,
                        file_path,
                        file_size,
                        now,
                        now,
                        result.get("quality_score"),
                        1 if result.get("needs_recheck") else 0,
                        result.get("quality_state") or "trusted",
                        json.dumps(result.get("quality_reasons_json") or []),
                        1 if result.get("review_required") else 0,
                    ),
                )
            else:
                db.execute(
                    """
                    UPDATE ingest_queue
                    SET status='transcribed',
                        transport_status='server_acked',
                        processing_status='transcribed',
                        processed_at=?,
                        error_code=NULL,
                        error_message=NULL,
                        quality_score=?,
                        needs_recheck=?,
                        quality_state=?,
                        quality_reasons_json=?,
                        review_required=?
                    WHERE id=?
                    """,
                    (
                        datetime.now(timezone.utc).isoformat(),
                        result.get("quality_score"),
                        1 if result.get("needs_recheck") else 0,
                        result.get("quality_state") or "trusted",
                        json.dumps(result.get("quality_reasons_json") or []),
                        1 if result.get("review_required") else 0,
                        file_id,
                    ),
                )

            existing = db.fetchone(
                "SELECT id FROM transcriptions WHERE ingest_id = ? LIMIT 1", (file_id,)
            )
            if existing:
                logger.debug(
                    "transcription_already_persisted", file_id=file_id, transcription_id=existing[0]
                )
                return existing[0]

            transcription_id = str(uuid.uuid4())
            text = result.get("text") or ""
            transcript_raw = result.get("transcript_raw") or text
            transcript_clean = result.get("transcript_clean") or text
            language = result.get("language")
            language_probability = result.get("language_probability")
            asr_model = result.get("asr_model")
            asr_confidence = result.get("asr_confidence")
            garbage_flag = 1 if result.get("garbage_flag") else 0
            quality_score = result.get("quality_score")
            needs_recheck = 1 if result.get("needs_recheck") else 0
            duration = result.get("duration")
            segments = result.get("segments")

            segments_str = None
            if segments is not None:
                import json

                try:
                    segments_str = (
                        json.dumps(segments) if not isinstance(segments, str) else segments
                    )
                except (TypeError, ValueError):
                    segments_str = None

            # ПОЧЕМУ speaker_* в INSERT: до этого фикса verification логировалась,
            # но не сохранялась — все записи имели speaker_confidence=0, is_user=1.
            speaker_confidence = result.get("speaker_confidence", 0.0)
            is_user = 1 if result.get("is_user", True) else 0
            speaker_id = result.get("speaker_id", 0)
            db.execute(
                """
                INSERT INTO transcriptions (
                    id, ingest_id, text, transcript_raw, transcript_clean,
                    language, language_probability, asr_model, asr_confidence,
                    garbage_flag, quality_score, needs_recheck,
                    quality_state, quality_reasons_json, review_required,
                    duration, segments, created_at, speaker_id, is_user, speaker_confidence, episode_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    transcription_id,
                    file_id,
                    transcript_clean,
                    transcript_raw,
                    transcript_clean,
                    language,
                    language_probability,
                    asr_model,
                    asr_confidence,
                    garbage_flag,
                    quality_score,
                    needs_recheck,
                    result.get("quality_state") or "trusted",
                    json.dumps(result.get("quality_reasons_json") or []),
                    1 if result.get("review_required") else 0,
                    duration,
                    segments_str,
                    datetime.now(timezone.utc).isoformat(),
                    speaker_id,
                    is_user,
                    speaker_confidence,
                ),
            )
        logger.info(
            "ws_transcription_persisted", file_id=file_id, transcription_id=transcription_id
        )
        return transcription_id
    except Exception as e:
        logger.exception("ws_transcription_persist_failed", file_id=file_id, error=str(e))
        return None
