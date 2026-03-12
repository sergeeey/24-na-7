from datetime import date
from unittest.mock import patch

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
                ("1", "received", "received", "2099-03-10 12:00:00", None, None),
                ("2", "asr_pending", "received", "2099-03-10 12:00:00", None, None),
                ("3", "event_ready", "server_acked", "2099-03-10 12:00:00", "2099-03-10 12:02:00", None),
                ("4", "retryable_error", "server_acked", "2099-03-10 12:00:00", "2099-03-10 12:03:00", "watchdog_stuck_received"),
                ("5", "filtered", "server_acked", "2099-03-10 12:00:00", "2099-03-10 12:01:00", None),
                ("6", "quarantined", "server_acked", "2099-03-10 12:00:00", "2099-03-10 12:04:00", None),
                ("7", "transcribed", "deduplicated", "2099-03-10 12:00:00", "2099-03-10 12:01:30", "asr_runtime_error"),
            ]
            for ingest_id, status, transport_status, created_at, processed_at, error_code in rows:
                db.execute(
                    """
                    INSERT INTO ingest_queue (
                        id, segment_id, filename, file_path, file_size, status,
                        transport_status, processing_status, created_at, processed_at, error_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        created_at,
                        processed_at,
                        error_code,
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
                    open_questions, commitments_json, topics_json, participants_json, carryover_candidate,
                    topic_overlap_score, participant_overlap_score,
                    temporal_proximity_score, commitment_overlap_score,
                    thread_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "thread-1",
                    "2026-03-10",
                    "work",
                    '["ep-trusted"]',
                    "storyline",
                    "",
                    "[]",
                    '["work"]',
                    '["Марат"]',
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
                INSERT INTO long_threads (
                    id, thread_key, first_seen_at, last_seen_at, day_thread_ids_json,
                    participants_json, topics_json, status, summary, continuity_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "lt-1",
                    "lt-key-1",
                    "2026-03-10",
                    "2026-03-10",
                    '["thread-1"]',
                    '["Марат"]',
                    '["work"]',
                    "active",
                    "рабочая линия",
                    0.9,
                ),
            )
            db.execute("UPDATE day_threads SET long_thread_key = ? WHERE id = ?", ("lt-1", "thread-1"))
            db.execute("UPDATE episodes SET long_thread_key = ? WHERE id = ?", ("lt-1", "ep-trusted"))
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
        with patch(
            "src.llm.providers.get_llm_circuit_breaker_stats",
            return_value={
                "openai": {
                    "name": "openai_llm",
                    "state": "closed",
                    "failure_count": 0,
                    "failure_threshold": 5,
                    "last_failure_time": None,
                    "timeout": 60,
                },
                "anthropic": {
                    "name": "anthropic_llm",
                    "state": "half_open",
                    "failure_count": 1,
                    "failure_threshold": 5,
                    "last_failure_time": 123.0,
                    "timeout": 60,
                },
                "google": {
                    "name": "google_llm",
                    "state": "open",
                    "failure_count": 5,
                    "failure_threshold": 5,
                    "last_failure_time": 456.0,
                    "timeout": 60,
                },
            },
        ):
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
        assert payload["ingest_health"]["stale_counts"]["received"] == 0
        assert payload["ingest_health"]["stale_counts"]["asr_pending"] == 0
        assert payload["ingest_health"]["recovery_counts"]["watchdog_retryable"] == 1
        assert payload["ingest_health"]["recovery_counts"]["asr_runtime_retryable"] == 0
        assert payload["ingest_health"]["latency_ms"]["received_to_terminal_avg"] == 138000.0
        assert payload["ingest_health"]["latency_ms"]["received_to_event_ready_avg"] == 120000.0
        assert payload["llm_circuit_breakers"]["state"] == "open"
        assert payload["llm_circuit_breakers"]["open_providers"] == ["google"]
        assert payload["llm_circuit_breakers"]["half_open_providers"] == ["anthropic"]
        assert payload["llm_circuit_breakers"]["providers"]["openai"]["state"] == "closed"
        assert payload["day_thread_counts"]["total"] == 1
        assert payload["day_thread_counts"]["trusted"] == 1
        assert payload["day_thread_counts"]["low_confidence"] == 0
        assert payload["long_thread_counts"]["total"] == 1
        assert payload["long_thread_counts"]["active"] == 1
        assert payload["long_thread_counts"]["resolved"] == 0
        assert payload["memory_health"]["trusted_fraction"] == 0.25
        assert payload["memory_health"]["review_fraction"] == 0.75
        assert payload["memory_health"]["thread_coverage"] == 0.5
        assert payload["memory_health"]["digest_incomplete_context_total"] == 1
        assert payload["memory_health"]["degraded_digest_candidate"] is True
        assert payload["slo_state"]["status"] == "attention"
        assert "low_trusted_fraction" in payload["slo_state"]["alerts"]
        assert "ingest_quarantine_present" in payload["slo_state"]["alerts"]
        assert "degraded_digest_present" in payload["slo_state"]["alerts"]
        assert payload["slo_state"]["beta_thresholds"]["min_trusted_fraction"] == 0.5
        assert payload["slo_state"]["snapshot"]["episodes_summarized"] == 2
        assert payload["slo_state"]["snapshot"]["day_threads_trusted"] == 1
        assert payload["slo_state"]["snapshot"]["stale_received"] == 0
        assert payload["slo_state"]["snapshot"]["stale_asr_pending"] == 0
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_ingest_watchdog_reaps_stale_received_and_asr_pending(tmp_path):
    from src.core.bootstrap import _run_ingest_watchdog
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
                ("old-received", "received", "received", "2026-03-10T10:00:00"),
                ("old-asr", "asr_pending", "asr_pending", "2026-03-10T10:00:00"),
                ("fresh-asr", "asr_pending", "asr_pending", "2099-03-10T10:00:00"),
            ]
            for ingest_id, status, processing_status, created_at in rows:
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
                        "server_acked",
                        processing_status,
                        created_at,
                    ),
                )

        _run_ingest_watchdog()

        old_received = db.fetchone(
            "SELECT status, processing_status, error_code FROM ingest_queue WHERE id = ?",
            ("old-received",),
        )
        old_asr = db.fetchone(
            "SELECT status, processing_status, error_code FROM ingest_queue WHERE id = ?",
            ("old-asr",),
        )
        fresh_asr = db.fetchone(
            "SELECT status, processing_status, error_code FROM ingest_queue WHERE id = ?",
            ("fresh-asr",),
        )

        assert old_received["status"] == "retryable_error"
        assert old_received["processing_status"] == "received"
        assert old_received["error_code"] == "watchdog_stuck_received"
        assert old_asr["status"] == "retryable_error"
        assert old_asr["processing_status"] == "asr_pending"
        assert old_asr["error_code"] == "watchdog_stuck_asr_pending"
        assert fresh_asr["status"] == "asr_pending"
        assert fresh_asr["processing_status"] == "asr_pending"
        assert fresh_asr["error_code"] is None
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_recover_retryable_ingest_tasks_requeues_and_quarantines_missing(tmp_path):
    from src.ingest.worker import IngestWorker, recover_retryable_ingest_tasks
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    uploads_path = storage_path / "uploads"
    storage_path.mkdir()
    uploads_path.mkdir()

    db_path = storage_path / "reflexio.db"
    ensure_ingest_tables(db_path)
    audio_path = uploads_path / "retry.wav"
    audio_path.write_bytes(
        b"RIFF$\x00\x00\x00WAVEfmt " + b"\x10\x00\x00\x00\x01\x00\x01\x00" +
        b"\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )
    db = get_reflexio_db(db_path)
    with db.transaction():
        db.execute(
            """
            INSERT INTO ingest_queue (
                id, segment_id, filename, file_path, file_size, status,
                transport_status, processing_status, created_at, error_code, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ok-retry",
                "seg-ok",
                "retry.wav",
                str(audio_path),
                audio_path.stat().st_size,
                "retryable_error",
                "server_acked",
                "asr_pending",
                "2026-03-10T10:00:00",
                "watchdog_stuck_asr_pending",
                "boom",
            ),
        )
        db.execute(
            """
            INSERT INTO ingest_queue (
                id, segment_id, filename, file_path, file_size, status,
                transport_status, processing_status, created_at, error_code, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "missing-retry",
                "seg-missing",
                "missing.wav",
                str(uploads_path / "missing.wav"),
                44,
                "retryable_error",
                "server_acked",
                "received",
                "2026-03-10T10:00:00",
                "watchdog_stuck_received",
                "boom",
            ),
        )

    worker = IngestWorker(registry={})
    worker._running = True
    submitted: list[str] = []
    original_submit = worker.submit

    def _capture(task):
        submitted.append(task.ingest_id)
        original_submit(task)

    worker.submit = _capture  # type: ignore[method-assign]
    result = recover_retryable_ingest_tasks(worker, db_path=db_path, limit=10)

    ok_row = db.fetchone(
        "SELECT status, processing_status, error_code FROM ingest_queue WHERE id = ?",
        ("ok-retry",),
    )
    missing_row = db.fetchone(
        "SELECT status, processing_status, error_code, quarantine_reason FROM ingest_queue WHERE id = ?",
        ("missing-retry",),
    )

    assert result == {"requeued": 1, "missing_audio": 1}
    assert submitted == ["ok-retry"]
    assert ok_row["status"] == "received"
    assert ok_row["processing_status"] == "received"
    assert ok_row["error_code"] is None
    assert missing_row["status"] == "quarantined"
    assert missing_row["processing_status"] == "quarantined"
    assert missing_row["error_code"] == "missing_audio"
    assert missing_row["quarantine_reason"] == "missing_audio"


def test_recover_retryable_ingest_tasks_respects_limit(tmp_path):
    from src.ingest.worker import IngestWorker, recover_retryable_ingest_tasks
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    uploads_path = storage_path / "uploads"
    storage_path.mkdir()
    uploads_path.mkdir()

    db_path = storage_path / "reflexio.db"
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    with db.transaction():
        for idx in range(2):
            audio_path = uploads_path / f"retry-{idx}.wav"
            audio_path.write_bytes(
                b"RIFF$\x00\x00\x00WAVEfmt " + b"\x10\x00\x00\x00\x01\x00\x01\x00" +
                b"\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
            )
            db.execute(
                """
                INSERT INTO ingest_queue (
                    id, segment_id, filename, file_path, file_size, status,
                    transport_status, processing_status, created_at, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"retry-{idx}",
                    f"seg-{idx}",
                    audio_path.name,
                    str(audio_path),
                    audio_path.stat().st_size,
                    "retryable_error",
                    "server_acked",
                    "received",
                    f"2026-03-10T10:00:0{idx}",
                    "watchdog_stuck_received",
                ),
            )

    worker = IngestWorker(registry={})
    worker._running = True
    submitted: list[str] = []
    worker.submit = lambda task: submitted.append(task.ingest_id)  # type: ignore[method-assign]

    result = recover_retryable_ingest_tasks(worker, db_path=db_path, limit=1)

    remaining = db.fetchall(
        "SELECT id, status FROM ingest_queue WHERE status = 'retryable_error' ORDER BY id"
    )
    assert result == {"requeued": 1, "missing_audio": 0}
    assert len(submitted) == 1
    assert len(remaining) == 1


def test_pipeline_trends_include_ingest_metrics(tmp_path):
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
        today = date.today().isoformat()
        with db.transaction():
            rows = [
                ("rx-1", "received", None, None),
                ("ax-1", "asr_pending", None, None),
                ("ev-1", "event_ready", f"{today} 00:02:00", None),
                ("rt-1", "retryable_error", f"{today} 00:03:00", "watchdog_stuck_received"),
                ("q-1", "quarantined", f"{today} 00:04:00", None),
            ]
            for ingest_id, status, processed_at, error_code in rows:
                db.execute(
                    """
                    INSERT INTO ingest_queue (
                        id, segment_id, filename, file_path, file_size, status,
                        transport_status, processing_status, created_at, processed_at, error_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ingest_id,
                        f"seg-{ingest_id}",
                        f"{ingest_id}.wav",
                        f"/tmp/{ingest_id}.wav",
                        100,
                        status,
                        "server_acked",
                        status,
                        f"{today} 00:00:00",
                        processed_at,
                        error_code,
                    ),
                )
            structured_rows = [
                ("evt-1", "tr-1", f"{today}T00:01:00", 100.0),
                ("evt-2", "tr-2", f"{today}T00:02:00", 200.0),
                ("evt-3", "tr-3", f"{today}T00:03:00", 300.0),
            ]
            for event_id, transcription_id, created_at, latency_ms in structured_rows:
                db.execute(
                    """
                    INSERT INTO structured_events (
                        id, transcription_id, text, created_at, is_current, enrichment_latency_ms
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        transcription_id,
                        f"text-{event_id}",
                        created_at,
                        1,
                        latency_ms,
                    ),
                )

        client = TestClient(app)
        response = client.get("/ingest/pipeline-trends?days_back=1")
        assert response.status_code == 200
        payload = response.json()
        assert payload["days_back"] == 1
        recent_day = payload["recent_days"][0]
        assert recent_day["received_count"] == 1
        assert recent_day["asr_pending_count"] == 1
        assert recent_day["event_ready_count"] == 1
        assert recent_day["retryable_error_count"] == 1
        assert recent_day["quarantined_ingest_count"] == 1
        assert recent_day["avg_received_to_processed_ms"] == 180000.0
        assert recent_day["enrichment_latency_ms"]["p50"] == 200.0
        assert recent_day["enrichment_latency_ms"]["p95"] == 290.0
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
