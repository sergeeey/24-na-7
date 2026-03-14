from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.enrichment.worker import EnrichmentTask, EnrichmentWorker


def test_enrichment_worker_schedules_bounded_retry(tmp_path, monkeypatch):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    db_path = storage_path / "reflexio.db"
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    with db.transaction():
        db.execute(
            """
            INSERT INTO ingest_queue (
                id, filename, file_path, file_size, status,
                transport_status, processing_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ing-retry",
                "retry.wav",
                str(storage_path / "retry.wav"),
                44,
                "event_pending",
                "server_acked",
                "event_pending",
                "2026-03-12T10:00:00",
            ),
        )

    worker = EnrichmentWorker()
    worker._running = True
    fake_loop = asyncio.new_event_loop()
    worker._workers = [MagicMock(get_loop=lambda: fake_loop)]
    task = EnrichmentTask(
        db_path=db_path,
        transcription_id="tr-1",
        result={"ingest_id": "ing-retry"},
        enrichment_text="hello",
    )

    scheduled = {}

    def _capture(coro, loop):
        scheduled["coro"] = coro
        scheduled["loop"] = loop
        return MagicMock()

    monkeypatch.setattr("asyncio.run_coroutine_threadsafe", _capture)

    with patch("src.core.audio_processing._run_enrichment_sync", side_effect=RuntimeError("llm down")):
        worker._execute(task)

    row = db.fetchone(
        "SELECT status, processing_status, attempt_count, error_code, next_attempt_at FROM ingest_queue WHERE id = ?",
        ("ing-retry",),
    )
    assert row["status"] == "event_pending"
    assert row["processing_status"] == "event_pending"
    assert row["attempt_count"] == 1
    assert row["error_code"] == "enrichment_retry_pending"
    assert row["next_attempt_at"] is not None
    assert scheduled["loop"] is fake_loop
    scheduled["coro"].close()
    fake_loop.close()


def test_enrichment_worker_stops_retry_after_limit(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    db_path = storage_path / "reflexio.db"
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    with db.transaction():
        db.execute(
            """
            INSERT INTO ingest_queue (
                id, filename, file_path, file_size, status,
                transport_status, processing_status, created_at, attempt_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ing-fail",
                "fail.wav",
                str(storage_path / "fail.wav"),
                44,
                "event_pending",
                "server_acked",
                "event_pending",
                "2026-03-12T10:00:00",
                2,
            ),
        )

    worker = EnrichmentWorker()
    task = EnrichmentTask(
        db_path=db_path,
        transcription_id="tr-2",
        result={"ingest_id": "ing-fail"},
        enrichment_text="hello",
        attempt=2,
    )

    with patch("src.core.audio_processing._run_enrichment_sync", side_effect=RuntimeError("still down")):
        worker._execute(task)

    row = db.fetchone(
        "SELECT status, processing_status, error_code, next_attempt_at FROM ingest_queue WHERE id = ?",
        ("ing-fail",),
    )
    assert row["status"] == "transcribed"
    assert row["processing_status"] == "transcribed"
    assert row["error_code"] == "enrichment_failed"
    assert row["next_attempt_at"] is None


def test_run_sqlite_backup_creates_snapshot_and_prunes_old(tmp_path):
    from src.core.bootstrap import _run_sqlite_backup
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    (storage_path / "reflexio.db").write_bytes(b"sqlite")
    backup_dir = storage_path / "backups"
    backup_dir.mkdir()
    old_snapshot = backup_dir / (datetime.now() - timedelta(days=9)).strftime("reflexio.db.%Y%m%d")
    recent_snapshot = backup_dir / (datetime.now() - timedelta(days=2)).strftime("reflexio.db.%Y%m%d")
    old_snapshot.write_bytes(b"old")
    recent_snapshot.write_bytes(b"recent")

    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    try:
        _run_sqlite_backup()
        today_snapshot = backup_dir / datetime.now().strftime("reflexio.db.%Y%m%d")
        assert today_snapshot.exists()
        assert not old_snapshot.exists()
        assert recent_snapshot.exists()
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
