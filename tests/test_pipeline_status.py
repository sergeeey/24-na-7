from fastapi.testclient import TestClient

from src.api.main import app


def test_pipeline_status_exposes_stage_specific_counters(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            rows = [
                ("1", "received", "received"),
                ("2", "asr_pending", "received"),
                ("3", "event_ready", "server_acked"),
                ("4", "retryable_error", "server_acked"),
                ("5", "filtered", "server_acked"),
                ("6", "quarantined", "server_acked"),
                ("7", "transcribed", "deduplicated"),
            ]
            for ingest_id, status, transport_status in rows:
                db.execute(
                    """
                    INSERT INTO ingest_queue (
                        id, segment_id, filename, file_path, file_size, status,
                        transport_status, processing_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ingest_id,
                        f"seg-{ingest_id}",
                        f"{ingest_id}.wav",
                        f"/tmp/{ingest_id}.wav",
                        100,
                        status,
                        transport_status,
                        status,
                        "2026-03-10T12:00:00",
                    ),
                )

        client = TestClient(app)
        response = client.get("/ingest/pipeline-status")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ingest_queue"]["pending"] == 3
        assert payload["ingest_queue"]["processed"] == 1
        assert payload["ingest_queue"]["error"] == 1
        assert payload["ingest_queue"]["filtered"] == 1
        assert payload["ingest_queue"]["quarantine"] == 1
        assert payload["ingest_stage_counts"]["received"] == 1
        assert payload["ingest_stage_counts"]["deduplicated"] == 1
        assert payload["ingest_stage_counts"]["asr_pending"] == 1
        assert payload["ingest_stage_counts"]["transcribed"] == 1
        assert payload["ingest_stage_counts"]["event_ready"] == 1
        assert payload["ingest_stage_counts"]["retryable_error"] == 1
        assert payload["ingest_stage_counts"]["quarantined"] == 1
        assert payload["episode_counts"]["open"] == 0
        assert payload["episode_counts"]["closed"] == 0
        assert payload["episode_counts"]["summarized"] == 0
        assert payload["episode_counts"]["needs_review"] == 0
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
