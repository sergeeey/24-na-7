"""Cryptographic integrity chain for ingest artifacts."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger("storage.integrity")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_integrity_tables(db_path: Path) -> None:
    """Create integrity tables if absent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS integrity_events (
                id TEXT PRIMARY KEY,
                ingest_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                prev_hash TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_integrity_ingest_created ON integrity_events(ingest_id, created_at)"
        )
        conn.commit()
    finally:
        conn.close()


def _compute_hash(payload_bytes: bytes | None, payload_text: str | None) -> str:
    hasher = hashlib.sha256()
    if payload_bytes is not None:
        hasher.update(payload_bytes)
    elif payload_text is not None:
        hasher.update(payload_text.encode("utf-8", errors="ignore"))
    else:
        hasher.update(b"")
    return hasher.hexdigest()


def append_integrity_event(
    db_path: Path,
    ingest_id: str,
    stage: str,
    payload_bytes: bytes | None = None,
    payload_text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Append one event to integrity hash chain."""
    ensure_integrity_tables(db_path)
    event_id = str(uuid.uuid4())
    content_hash = _compute_hash(payload_bytes, payload_text)
    created_at = _now_iso()
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT content_hash
            FROM integrity_events
            WHERE ingest_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (ingest_id,),
        )
        row = cur.fetchone()
        prev_hash = row[0] if row else None

        cur.execute(
            """
            INSERT INTO integrity_events (id, ingest_id, stage, content_hash, prev_hash, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, ingest_id, stage, content_hash, prev_hash, metadata_json, created_at),
        )
        conn.commit()
        return event_id
    finally:
        conn.close()


def get_ingest_integrity_report(db_path: Path, ingest_id: str) -> dict[str, Any]:
    """Return chain validation report for one ingest_id."""
    ensure_integrity_tables(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, stage, content_hash, prev_hash, metadata, created_at
            FROM integrity_events
            WHERE ingest_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (ingest_id,),
        ).fetchall()

        events: list[dict[str, Any]] = []
        chain_valid = True
        expected_prev = None

        for row in rows:
            prev_hash = row["prev_hash"]
            if prev_hash != expected_prev:
                chain_valid = False
            expected_prev = row["content_hash"]
            try:
                metadata = json.loads(row["metadata"] or "{}")
            except Exception:
                metadata = {}
            events.append(
                {
                    "id": row["id"],
                    "stage": row["stage"],
                    "content_hash": row["content_hash"],
                    "prev_hash": prev_hash,
                    "metadata": metadata,
                    "created_at": row["created_at"],
                }
            )

        return {
            "ingest_id": ingest_id,
            "events": events,
            "events_count": len(events),
            "chain_valid": chain_valid,
        }
    finally:
        conn.close()
