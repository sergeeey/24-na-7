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

            episode_rows = [
                ("ep-trusted", "summarized", "trusted", 0),
                ("ep-uncertain", "closed", "uncertain", 1),
                ("ep-garbage", "open", "garbage", 1),
                ("ep-quarantined", "summarized", "quarantined", 1),
            ]
            for episode_id, status, quality_state, needs_review in episode_rows:
                db.execute(
                    """
                    INSERT INTO episodes (
                        id, started_at, ended_at, status, source_count, transcription_ids_json,
                        raw_text, clean_text, summary, topics_json, participants_json,
                        commitments_json, importance_score, needs_review, quality_state,
                        quality_score, quality_reasons_json, review_required, day_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id,
                        "2026-03-10T12:00:00",
                        "2026-03-10T12:01:00",
                        status,
                        1,
                        '["tr-1"]',
                        "текст",
                        "текст",
                        "summary",
                        '["work"]',
                        "[]",
                        "[]",
                        0.8,
                        needs_review,
                        quality_state,
                        0.8,
                        "[]",
                        needs_review,
                        "2026-03-10",
                    ),
                )
            db.execute(
                """
                INSERT INTO day_threads (
                    id, day_key, topic_cluster, episode_ids_json, summary,
                    open_questions, commitments_json, carryover_candidate,
                    topic_overlap_score, participant_overlap_score,
                    temporal_proximity_score, commitment_overlap_score,
                    thread_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "thread-1",
                    "2026-03-10",
                    "work",
                    '["ep-trusted"]',
                    "storyline",
                    "",
                    "[]",
                    0,
                    1.0,
                    1.0,
                    1.0,
                    0.0,
                    0.9,
                ),
            )
            db.execute(
                """
                INSERT INTO digest_cache (
                    date, digest_json, generated_at, status,
                    previous_digest_id, rebuild_reason, rebuilt_at, changed_source_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-03-10",
                    '{"incomplete_context": true, "degraded": true}',
                    "2026-03-10T13:00:00Z",
                    "ready",
                    None,
                    None,
                    None,
                    0,
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
        assert payload["episode_counts"]["open"] == 1
        assert payload["episode_counts"]["closed"] == 1
        assert payload["episode_counts"]["summarized"] == 2
        assert payload["episode_counts"]["needs_review"] == 3
        assert payload["quality_counts"]["trusted"] == 1
        assert payload["quality_counts"]["uncertain"] == 1
        assert payload["quality_counts"]["garbage"] == 1
        assert payload["quality_counts"]["quarantined"] == 1
        assert payload["day_thread_counts"]["total"] == 1
        assert payload["day_thread_counts"]["trusted"] == 1
        assert payload["day_thread_counts"]["low_confidence"] == 0
        assert payload["memory_health"]["trusted_fraction"] == 0.25
        assert payload["memory_health"]["review_fraction"] == 0.75
        assert payload["memory_health"]["thread_coverage"] == 0.5
        assert payload["memory_health"]["digest_incomplete_context_total"] == 1
        assert payload["memory_health"]["degraded_digest_candidate"] is True
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
