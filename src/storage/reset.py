"""Administrative reset helpers for wiping user-generated data."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.storage.db import get_reflexio_db
from src.utils.logging import get_logger

logger = get_logger("storage.reset")


USER_DATA_TABLES = (
    "digest_sources",
    "digest_cache",
    "digests",
    "facts",
    "recording_analyses",
    "day_threads",
    "episodes",
    "quality_state_transition_log",
    "structured_events",
    "transcriptions",
    "ingest_queue",
    "memory_nodes",
    "retrieval_traces",
    "person_graph_events",
    "person_interactions",
    "person_voice_samples",
    "person_voice_profiles",
    "persons",
    "integrity_events",
    "text_entries",
    "health_metrics",
)


@dataclass
class ResetAllReport:
    reset_at: str
    deleted_rows: dict[str, int]
    deleted_digest_files: int
    deleted_upload_files: int
    deleted_graph_projection: bool


def reset_all_user_data(storage_path: Path) -> ResetAllReport:
    """Delete all user-generated data while preserving schema and migrations."""
    db_path = storage_path / "reflexio.db"
    db = get_reflexio_db(db_path)
    existing_tables = {
        row["name"]
        for row in db.fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    deleted_rows: dict[str, int] = {}
    with db.transaction():
        for table in USER_DATA_TABLES:
            if table not in existing_tables:
                continue
            cursor = db.execute(f"DELETE FROM {table}")
            deleted_rows[table] = max(cursor.rowcount, 0)

        if "sqlite_sequence" in existing_tables:
            placeholders = ",".join("?" for _ in USER_DATA_TABLES)
            db.execute(
                f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
                tuple(USER_DATA_TABLES),
            )

    deleted_digest_files = _clear_directory_files(Path("digests"))
    deleted_upload_files = _clear_directory_files(storage_path / "uploads")
    deleted_graph_projection = _clear_graph_projection(storage_path / "graph.kuzu")

    report = ResetAllReport(
        reset_at=datetime.now(timezone.utc).isoformat(),
        deleted_rows=deleted_rows,
        deleted_digest_files=deleted_digest_files,
        deleted_upload_files=deleted_upload_files,
        deleted_graph_projection=deleted_graph_projection,
    )
    logger.warning(
        "admin_reset_all_completed",
        reset_at=report.reset_at,
        deleted_rows=report.deleted_rows,
        deleted_digest_files=report.deleted_digest_files,
        deleted_upload_files=report.deleted_upload_files,
        deleted_graph_projection=report.deleted_graph_projection,
    )
    return report


def _clear_directory_files(path: Path) -> int:
    if not path.exists():
        return 0

    deleted = 0
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            deleted += 1
        else:
            child.unlink(missing_ok=True)
            deleted += 1
    return deleted


def _clear_graph_projection(path: Path) -> bool:
    if not path.exists():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True
