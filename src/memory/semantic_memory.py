"""Semantic memory consolidation and retrieval."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger("memory.semantic")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_semantic_memory_tables(db_path: Path) -> None:
    """Create semantic memory and retrieval trace tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_nodes (
                id TEXT PRIMARY KEY,
                source_ingest_id TEXT,
                source_transcription_id TEXT,
                content TEXT NOT NULL,
                summary TEXT,
                topics_json TEXT,
                entities_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_nodes_created ON memory_nodes(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_nodes_ingest ON memory_nodes(source_ingest_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS retrieval_traces (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                node_ids_json TEXT,
                top_k INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _extract_entities(text: str, limit: int = 20) -> list[str]:
    tokens = []
    for raw in (text or "").replace("\n", " ").split(" "):
        token = raw.strip(" .,!?()[]{}:;\"'").lower()
        if len(token) < 4:
            continue
        if not token.isalpha():
            continue
        tokens.append(token)
    uniq = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        uniq.append(token)
        seen.add(token)
        if len(uniq) >= limit:
            break
    return uniq


def consolidate_to_memory_node(
    db_path: Path,
    ingest_id: str,
    transcription_id: str | None,
    text: str,
    summary: str | None = None,
    topics: list[str] | None = None,
) -> str:
    """Save one consolidated memory node from transcription/enrichment."""
    ensure_semantic_memory_tables(db_path)
    node_id = str(uuid.uuid4())
    created_at = _now_iso()
    topics_json = json.dumps(topics or [], ensure_ascii=False)
    entities_json = json.dumps(_extract_entities(text), ensure_ascii=False)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO memory_nodes (
                id, source_ingest_id, source_transcription_id,
                content, summary, topics_json, entities_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                ingest_id,
                transcription_id,
                text,
                summary or "",
                topics_json,
                entities_json,
                created_at,
            ),
        )
        conn.commit()
        return node_id
    finally:
        conn.close()


def retrieve_memory(db_path: Path, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Simple retrieval from semantic memory with transparent evidence."""
    ensure_semantic_memory_tables(db_path)
    if not query.strip():
        return []

    q = f"%{query.strip().lower()}%"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, source_ingest_id, source_transcription_id, content, summary, topics_json, entities_json, created_at
            FROM memory_nodes
            WHERE lower(content) LIKE ? OR lower(summary) LIKE ? OR lower(entities_json) LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (q, q, q, top_k),
        ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                topics = json.loads(row["topics_json"] or "[]")
            except Exception:
                topics = []
            try:
                entities = json.loads(row["entities_json"] or "[]")
            except Exception:
                entities = []

            results.append(
                {
                    "node_id": row["id"],
                    "source_ingest_id": row["source_ingest_id"],
                    "source_transcription_id": row["source_transcription_id"],
                    "summary": row["summary"],
                    "content": row["content"],
                    "topics": topics,
                    "entities": entities,
                    "created_at": row["created_at"],
                }
            )

        return results
    finally:
        conn.close()


def record_retrieval_trace(db_path: Path, query: str, node_ids: list[str], top_k: int) -> str:
    """Record retrieval trace for auditability."""
    ensure_semantic_memory_tables(db_path)
    trace_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO retrieval_traces (id, query, node_ids_json, top_k, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (trace_id, query, json.dumps(node_ids), top_k, _now_iso()),
        )
        conn.commit()
        return trace_id
    finally:
        conn.close()
