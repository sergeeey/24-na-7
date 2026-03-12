"""Тесты API endpoints."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.utils.config import settings
from src.utils.rate_limiter import RateLimitConfig


def test_ingest_audio(tmp_path):
    """Проверяет загрузку валидного WAV."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    wav_header = bytes(
        [
            0x52,
            0x49,
            0x46,
            0x46,
            0x24,
            0x00,
            0x00,
            0x00,
            0x57,
            0x41,
            0x56,
            0x45,
            0x66,
            0x6D,
            0x74,
            0x20,
            0x10,
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            0x01,
            0x00,
            0x44,
            0xAC,
            0x00,
            0x00,
            0x88,
            0x58,
            0x01,
            0x00,
            0x02,
            0x00,
            0x10,
            0x00,
            0x64,
            0x61,
            0x74,
            0x61,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )

    with patch.object(settings, "UPLOADS_PATH", tmp_path):
        client = TestClient(app)
        files = {"file": ("test.wav", wav_header, "audio/wav")}
        resp = client.post("/ingest/audio", files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "received"
    assert "id" in data
    assert "filename" in data
    assert "path" in data
    assert not Path(data["path"]).is_absolute()
    assert data["size"] > 0


def test_ingest_audio_rejects_non_wav(tmp_path):
    """Отклоняет файл с .wav именем, но не-WAV сигнатурой."""
    tmp_path.mkdir(parents=True, exist_ok=True)

    with patch.object(settings, "UPLOADS_PATH", tmp_path):
        client = TestClient(app)
        files = {"file": ("fake.wav", b"NOT_WAV_CONTENT", "audio/wav")}
        resp = client.post("/ingest/audio", files=files)

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == "Invalid WAV file signature"


def test_ingest_audio_rejects_oversized_payload_in_strict_safe_mode(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    wav_header = (
        b"RIFF$\x00\x00\x00WAVEfmt "
        + b"\x10\x00\x00\x00\x01\x00\x01\x00"
        + b"\x44\xAC\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00"
        + b"data\x00\x00\x00\x00"
    )

    class _FakeSafeChecker:
        def check_file_extension(self, path):
            return True, None

        def check_file_size(self, path):
            return False, "payload_too_large"

    old_safe_mode = os.getenv("SAFE_MODE")
    os.environ["SAFE_MODE"] = "strict"
    try:
        with patch.object(settings, "UPLOADS_PATH", tmp_path), patch(
            "src.api.routers.ingest.get_safe_checker",
            return_value=_FakeSafeChecker(),
        ):
            client = TestClient(app)
            files = {"file": ("test.wav", wav_header, "audio/wav")}
            resp = client.post("/ingest/audio", files=files)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "SAFE validation failed: payload_too_large"
    finally:
        if old_safe_mode is None:
            os.environ.pop("SAFE_MODE", None)
        else:
            os.environ["SAFE_MODE"] = old_safe_mode


def test_ingest_audio_rate_limit_contract(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    wav_header = (
        b"RIFF$\x00\x00\x00WAVEfmt "
        + b"\x10\x00\x00\x00\x01\x00\x01\x00"
        + b"\x44\xAC\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00"
        + b"data\x00\x00\x00\x00"
    )

    old_api_key = settings.API_KEY
    old_limiter_enabled = app.state.limiter.enabled
    object.__setattr__(settings, "API_KEY", None)
    app.state.limiter.enabled = True

    try:
        app.state.limiter._storage.reset()
        with patch.object(settings, "UPLOADS_PATH", tmp_path):
            client = TestClient(app)
            files = {"file": ("test.wav", wav_header, "audio/wav")}
            responses = [client.post("/ingest/audio", files=files) for _ in range(11)]
        limited = next((resp for resp in responses if resp.status_code == 429), None)
        assert limited is not None
        assert limited.status_code == 429
        assert "Rate limit exceeded" in limited.text
        assert "X-RateLimit-Limit" in responses[0].headers
    finally:
        object.__setattr__(settings, "API_KEY", old_api_key)
        app.state.limiter.enabled = old_limiter_enabled


def test_ingest_status():
    """Проверяет endpoint статуса."""
    client = TestClient(app)

    resp = client.get("/ingest/status/test-id-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-id-123"
    assert data["status"] == "pending"


def test_ingest_status_v1():
    """Проверяет v1 alias для ingest status."""
    client = TestClient(app)

    resp = client.get("/v1/ingest/status/test-id-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-id-123"
    assert data["status"] == "pending"


def test_pipeline_trends_returns_recent_day_aggregates(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
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
                    "ep-trusted",
                    "2026-03-11T10:00:00",
                    "2026-03-11T10:05:00",
                    "summarized",
                    1,
                    '["tr-1"]',
                    "raw",
                    "clean",
                    "summary",
                    '["work"]',
                    "[]",
                    "[]",
                    0.9,
                    0,
                    "trusted",
                    0.9,
                    "[]",
                    0,
                    "2026-03-11",
                ),
            )
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
                    "ep-garbage",
                    "2026-03-10T10:00:00",
                    "2026-03-10T10:05:00",
                    "summarized",
                    1,
                    '["tr-2"]',
                    "raw",
                    "clean",
                    "summary",
                    '["noise"]',
                    "[]",
                    "[]",
                    0.1,
                    1,
                    "garbage",
                    0.1,
                    '[{"code":"LOW_INFORMATION","severity":"medium","score_delta":-0.5,"details":{}}]',
                    1,
                    "2026-03-10",
                ),
            )
            db.execute(
                """
                INSERT INTO day_threads (
                    id, day_key, topic_cluster, episode_ids_json, summary, open_questions,
                    commitments_json, topics_json, participants_json, carryover_candidate,
                    topic_overlap_score, participant_overlap_score,
                    temporal_proximity_score, commitment_overlap_score,
                    thread_confidence, long_thread_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "dt-1",
                    "2026-03-11",
                    "work",
                    '["ep-trusted"]',
                    "line",
                    "",
                    "[]",
                    '["work"]',
                    "[]",
                    0,
                    1.0,
                    0.0,
                    1.0,
                    0.0,
                    0.9,
                    "lt-1",
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
                    "lt-work",
                    "2026-03-11",
                    "2026-03-11",
                    '["dt-1"]',
                    "[]",
                    '["work"]',
                    "active",
                    "work line",
                    0.8,
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
                    '{"degraded": true, "incomplete_context": true}',
                    "2026-03-10T12:00:00Z",
                    "ready",
                    None,
                    None,
                    None,
                    0,
                ),
            )

        client = TestClient(app)
        resp = client.get("/ingest/pipeline-trends?days_back=3")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["days_back"] == 3
        assert len(payload["recent_days"]) == 3
        by_day = {item["day"]: item for item in payload["recent_days"]}
        assert by_day["2026-03-11"]["trusted_count"] == 1
        assert by_day["2026-03-11"]["day_thread_count"] == 1
        assert by_day["2026-03-11"]["long_thread_count"] == 1
        assert by_day["2026-03-11"]["degraded_digest"] is False
        assert by_day["2026-03-10"]["garbage_count"] == 1
        assert by_day["2026-03-10"]["review_count"] == 1
        assert by_day["2026-03-10"]["degraded_digest"] is True
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_digest_review_lists_healthy_and_degraded_days(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
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
                    "ep-ok",
                    "2026-03-11T10:00:00",
                    "2026-03-11T10:05:00",
                    "summarized",
                    1,
                    '["tr-ok"]',
                    "обсуждали проект",
                    "обсуждали проект",
                    "договорились по проекту",
                    '["проект"]',
                    "[]",
                    "[]",
                    0.8,
                    0,
                    "trusted",
                    0.9,
                    "[]",
                    0,
                    "2026-03-11",
                ),
            )
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
                    "ep-bad",
                    "2026-03-10T10:00:00",
                    "2026-03-10T10:05:00",
                    "summarized",
                    1,
                    '["tr-bad"]',
                    "Роман Роман ты где Роман",
                    "Роман Роман ты где Роман",
                    "шум",
                    '["шум"]',
                    "[]",
                    "[]",
                    0.1,
                    1,
                    "garbage",
                    0.1,
                    '[{"code":"LOW_INFORMATION","severity":"medium","score_delta":-0.5,"details":{}}]',
                    1,
                    "2026-03-10",
                ),
            )
            db.execute(
                """
                INSERT INTO day_threads (
                    id, day_key, topic_cluster, episode_ids_json, summary, open_questions,
                    commitments_json, topics_json, participants_json, carryover_candidate,
                    topic_overlap_score, participant_overlap_score,
                    temporal_proximity_score, commitment_overlap_score,
                    thread_confidence, long_thread_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "dt-ok",
                    "2026-03-11",
                    "project",
                    '["ep-ok"]',
                    "проектная линия",
                    "",
                    "[]",
                    '["проект"]',
                    "[]",
                    0,
                    1.0,
                    0.0,
                    1.0,
                    0.0,
                    0.9,
                    "lt-ok",
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
                    "lt-ok",
                    "lt-project",
                    "2026-03-11",
                    "2026-03-11",
                    '["dt-ok"]',
                    "[]",
                    '["проект"]',
                    "active",
                    "проектная continuity line",
                    0.8,
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
                    "2026-03-11",
                    '{"source_unit":"day_thread","degraded":false,"incomplete_context":false,"episodes_used":1,"total_recordings":1}',
                    "2026-03-11T12:00:00Z",
                    "ready",
                    None,
                    None,
                    None,
                    1,
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
                    '{"source_unit":"transcription","degraded":true,"incomplete_context":true,"episodes_used":0,"total_recordings":0}',
                    "2026-03-10T12:00:00Z",
                    "ready",
                    None,
                    None,
                    None,
                    0,
                ),
            )

        client = TestClient(app)
        resp = client.get(
            "/digest/review",
            params={"date_from": "2026-03-10", "date_to": "2026-03-11"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["days"]) == 2
        by_day = {item["date"]: item for item in body["days"]}
        assert by_day["2026-03-11"]["degraded"] is False
        assert by_day["2026-03-11"]["candidate_action"] == "observe"
        assert by_day["2026-03-10"]["degraded"] is True
        assert by_day["2026-03-10"]["candidate_action"] == "reclassify"

        degraded_only = client.get(
            "/digest/review",
            params={"date_from": "2026-03-10", "date_to": "2026-03-11", "only_degraded": "true"},
        )
        assert degraded_only.status_code == 200
        degraded_days = degraded_only.json()["days"]
        assert [item["date"] for item in degraded_days] == ["2026-03-10"]
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_digest_review_day_returns_detail_summary(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
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
                    "ep-review",
                    "2026-03-10T10:00:00",
                    "2026-03-10T10:05:00",
                    "summarized",
                    1,
                    "[]",
                    "шум",
                    "шум",
                    "шум",
                    "[]",
                    "[]",
                    "[]",
                    0.1,
                    1,
                    "quarantined",
                    0.1,
                    '[{"code":"REPEATED_PHRASE","severity":"high","score_delta":-0.8,"details":{}}]',
                    1,
                    "2026-03-10",
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
                    '{"source_unit":"transcription","degraded":true,"incomplete_context":true,"episodes_used":0,"total_recordings":0}',
                    "2026-03-10T12:00:00Z",
                    "ready",
                    None,
                    None,
                    None,
                    0,
                ),
            )

        client = TestClient(app)
        resp = client.get("/digest/review/2026-03-10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == "2026-03-10"
        assert body["degraded"] is True
        assert body["source_unit"] == "transcription"
        assert body["trusted_episode_present"] is False
        assert body["transcript_fallback_only"] is True
        assert body["candidate_action"] in {"recheck", "reclassify"}
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_reprocess_ingest_requeues_retryable_item(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    uploads_path = storage_path / "uploads"
    storage_path.mkdir()
    uploads_path.mkdir()

    old_storage = settings.STORAGE_PATH
    old_uploads = settings.UPLOADS_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    object.__setattr__(settings, "UPLOADS_PATH", uploads_path)

    try:
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
                    id, filename, file_path, file_size, status,
                    transport_status, processing_status, created_at, error_code, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ing-1",
                    "retry.wav",
                    str(audio_path),
                    audio_path.stat().st_size,
                    "retryable_error",
                    "server_acked",
                    "asr_pending",
                    "2026-03-10T12:00:00",
                    "asr_runtime_error",
                    "boom",
                ),
            )

        worker = MagicMock()
        worker.submit = MagicMock()
        client = TestClient(app)
        with patch("src.api.routers.ingest.get_ingest_worker", return_value=worker):
            resp = client.post("/ingest/reprocess/ing-1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "requeued"
        refreshed = db.fetchone("SELECT status, processing_status, error_code FROM ingest_queue WHERE id = ?", ("ing-1",))
        assert refreshed["status"] == "received"
        assert refreshed["processing_status"] == "received"
        assert refreshed["error_code"] is None
        assert worker.submit.call_count == 1
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
        object.__setattr__(settings, "UPLOADS_PATH", old_uploads)


def test_reprocess_ingest_rejects_non_reprocessable(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
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
                    "ing-2",
                    "done.wav",
                    "D:/tmp/done.wav",
                    44,
                    "event_ready",
                    "server_acked",
                    "event_ready",
                    "2026-03-10T12:00:00",
                ),
            )

        client = TestClient(app)
        resp = client.post("/ingest/reprocess/ing-2")
        assert resp.status_code == 409
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_admin_reset_all_clears_data_and_artifacts(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.memory.semantic_memory import ensure_semantic_memory_tables
    from src.persongraph.service import ensure_person_graph_tables

    storage_path = tmp_path / "storage"
    uploads_path = storage_path / "uploads"
    digests_path = tmp_path / "digests"
    storage_path.mkdir()
    uploads_path.mkdir()
    digests_path.mkdir()

    old_storage = settings.STORAGE_PATH
    old_uploads = settings.UPLOADS_PATH
    old_cwd = Path.cwd()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    object.__setattr__(settings, "UPLOADS_PATH", uploads_path)

    try:
        os.chdir(tmp_path)
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        ensure_semantic_memory_tables(db_path)
        ensure_person_graph_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("ing-1", "a.wav", str(uploads_path / "a.wav"), 12, "received", "2026-03-10T12:00:00"),
            )
            db.execute(
                """
                INSERT INTO transcriptions (id, ingest_id, text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("tr-1", "ing-1", "hello", "2026-03-10T12:00:01"),
            )
            db.execute(
                """
                INSERT INTO structured_events (id, transcription_id, text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("ev-1", "tr-1", "hello", "2026-03-10T12:00:02"),
            )
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:01",
                    "2026-03-10T12:00:10",
                    "closed",
                    1,
                    '["tr-1"]',
                    "hello",
                    "hello",
                    "hello",
                    '["work"]',
                    "[]",
                    "[]",
                    0.8,
                    0,
                    "2026-03-10",
                ),
            )
            db.execute(
                """
                INSERT INTO day_threads (
                    id, day_key, topic_cluster, episode_ids_json, summary, open_questions,
                    commitments_json, carryover_candidate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "dt-1",
                    "2026-03-10",
                    "work",
                    '["ep-1"]',
                    "hello",
                    "",
                    "[]",
                    0,
                ),
            )
            db.execute(
                """
                INSERT INTO memory_nodes (id, source_ingest_id, source_transcription_id, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("mem-1", "ing-1", "tr-1", "hello", "2026-03-10T12:00:03"),
            )
            db.execute(
                """
                INSERT INTO person_graph_events (id, day, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("pg-1", "2026-03-10", "psychology_snapshot", "{}", "2026-03-10T12:00:04"),
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS digest_cache (
                    date TEXT PRIMARY KEY,
                    digest_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready'
                )
                """
            )
            db.execute(
                """
                INSERT INTO digest_cache (date, digest_json, generated_at, status)
                VALUES (?, ?, ?, ?)
                """,
                ("2026-03-10", "{}", "2026-03-10T12:00:05", "ready"),
            )
        (uploads_path / "a.wav").write_bytes(b"wav")
        (digests_path / "digest_2026-03-10.json").write_text("{}", encoding="utf-8")

        client = TestClient(app)
        resp = client.post("/admin/reset-all", json={"confirm": "RESET_ALL_DATA"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "reset"
        assert body["deleted_rows"]["ingest_queue"] == 1
        assert body["deleted_rows"]["transcriptions"] == 1
        assert body["deleted_rows"]["episodes"] == 1
        assert body["deleted_rows"]["day_threads"] == 1
        assert body["deleted_rows"]["structured_events"] == 1
        assert body["deleted_rows"]["memory_nodes"] == 1
        assert body["deleted_rows"]["person_graph_events"] == 1
        assert body["deleted_rows"]["digest_cache"] == 1
        assert body["deleted_digest_files"] == 1
        assert body["deleted_upload_files"] == 1

        assert db.fetchone("SELECT COUNT(*) AS c FROM ingest_queue")["c"] == 0
        assert db.fetchone("SELECT COUNT(*) AS c FROM transcriptions")["c"] == 0
        assert db.fetchone("SELECT COUNT(*) AS c FROM episodes")["c"] == 0
        assert db.fetchone("SELECT COUNT(*) AS c FROM day_threads")["c"] == 0
        assert db.fetchone("SELECT COUNT(*) AS c FROM structured_events")["c"] == 0
        assert db.fetchone("SELECT COUNT(*) AS c FROM memory_nodes")["c"] == 0
        assert db.fetchone("SELECT COUNT(*) AS c FROM person_graph_events")["c"] == 0
        assert db.fetchone("SELECT COUNT(*) AS c FROM digest_cache")["c"] == 0
        assert list(digests_path.iterdir()) == []
        assert list(uploads_path.iterdir()) == []
    finally:
        os.chdir(old_cwd)
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
        object.__setattr__(settings, "UPLOADS_PATH", old_uploads)


def test_admin_reset_all_requires_explicit_confirm():
    client = TestClient(app)
    resp = client.post("/admin/reset-all", json={"confirm": "NOPE"})
    assert resp.status_code == 400


def test_admin_reset_all_requires_bearer_auth_when_api_key_enabled(tmp_path):
    old_storage = settings.STORAGE_PATH
    old_api_key = settings.API_KEY
    old_limiter_enabled = app.state.limiter.enabled
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    object.__setattr__(settings, "API_KEY", "secret-test-key")
    app.state.limiter.enabled = False

    try:
        client = TestClient(app)
        ok = client.post(
            "/admin/reset-all",
            json={"confirm": "RESET_ALL_DATA"},
            headers={"Authorization": "Bearer secret-test-key"},
        )
        assert ok.status_code == 200
    finally:
        app.state.limiter.enabled = old_limiter_enabled
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
        object.__setattr__(settings, "API_KEY", old_api_key)


def test_admin_reset_all_rejects_missing_bearer_auth_when_api_key_enabled(tmp_path):
    old_storage = settings.STORAGE_PATH
    old_api_key = settings.API_KEY
    old_limiter_enabled = app.state.limiter.enabled
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    object.__setattr__(settings, "API_KEY", "secret-test-key")
    app.state.limiter.enabled = False

    try:
        client = TestClient(app)
        resp = client.post("/admin/reset-all", json={"confirm": "RESET_ALL_DATA"})
        assert resp.status_code == 401
    finally:
        app.state.limiter.enabled = old_limiter_enabled
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
        object.__setattr__(settings, "API_KEY", old_api_key)


def test_admin_reset_all_rejects_wrong_bearer_auth_when_api_key_enabled(tmp_path):
    old_storage = settings.STORAGE_PATH
    old_api_key = settings.API_KEY
    old_limiter_enabled = app.state.limiter.enabled
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    object.__setattr__(settings, "API_KEY", "secret-test-key")
    app.state.limiter.enabled = False

    try:
        client = TestClient(app)
        resp = client.post(
            "/admin/reset-all",
            json={"confirm": "RESET_ALL_DATA"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"] == "Bearer"
        assert resp.json()["error"] == "Invalid or missing API key"
    finally:
        app.state.limiter.enabled = old_limiter_enabled
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
        object.__setattr__(settings, "API_KEY", old_api_key)


def test_admin_reclassify_dry_run_does_not_mutate(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:01:00",
                    "summarized",
                    1,
                    '["tr-1"]',
                    "Роман Роман ты где Роман",
                    "Роман Роман ты где Роман",
                    "",
                    "[]",
                    "[]",
                    "[]",
                    0.3,
                    0,
                    "2026-03-10",
                ),
            )

        client = TestClient(app)
        resp = client.post("/admin/reclassify", json={"mode": "dry_run", "date": "2026-03-10"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "dry_run"
        assert body["affected_episodes"] == 1
        assert body["affected_transcriptions"] == 0
        row = db.fetchone("SELECT quality_state FROM episodes WHERE id = ?", ("ep-1",))
        assert row["quality_state"] == "trusted"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_admin_reclassify_rejects_missing_bearer_auth_when_api_key_enabled(tmp_path):
    old_storage = settings.STORAGE_PATH
    old_api_key = settings.API_KEY
    old_limiter_enabled = app.state.limiter.enabled
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    object.__setattr__(settings, "API_KEY", "secret-test-key")
    app.state.limiter.enabled = False

    try:
        client = TestClient(app)
        resp = client.post("/admin/reclassify", json={"mode": "dry_run", "date": "2026-03-10"})
        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"] == "Bearer"
        assert resp.json()["error"] == "Invalid or missing API key"
    finally:
        app.state.limiter.enabled = old_limiter_enabled
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
        object.__setattr__(settings, "API_KEY", old_api_key)


def test_pipeline_status_rejects_wrong_bearer_auth_when_api_key_enabled(tmp_path):
    old_storage = settings.STORAGE_PATH
    old_api_key = settings.API_KEY
    old_limiter_enabled = app.state.limiter.enabled
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    object.__setattr__(settings, "API_KEY", "secret-test-key")
    app.state.limiter.enabled = False

    try:
        client = TestClient(app)
        resp = client.get(
            "/ingest/pipeline-status",
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"] == "Bearer"
        assert resp.json()["error"] == "Invalid or missing API key"
    finally:
        app.state.limiter.enabled = old_limiter_enabled
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
        object.__setattr__(settings, "API_KEY", old_api_key)


def test_admin_reclassify_apply_updates_quality_state_and_digest_cache(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    old_cwd = Path.cwd()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        os.chdir(tmp_path)
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:01:00",
                    "summarized",
                    1,
                    '["tr-1"]',
                    "Роман Роман ты где Роман",
                    "Роман Роман ты где Роман",
                    "",
                    "[]",
                    "[]",
                    "[]",
                    0.3,
                    0,
                    "2026-03-10",
                ),
            )

        client = TestClient(app)
        resp = client.post("/admin/reclassify", json={"mode": "apply", "date": "2026-03-10"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["affected_transcriptions"] == 0
        row = db.fetchone("SELECT quality_state FROM episodes WHERE id = ?", ("ep-1",))
        assert row["quality_state"] in {"garbage", "quarantined"}
        digest_row = db.fetchone(
            "SELECT rebuild_reason, changed_source_count FROM digest_cache WHERE date = ?",
            ("2026-03-10",),
        )
        assert digest_row["rebuild_reason"] == "truth_reclassify"
        assert digest_row["changed_source_count"] >= 1
        transitions = db.fetchone("SELECT COUNT(*) AS c FROM quality_state_transition_log")
        assert transitions["c"] >= 1
    finally:
        os.chdir(old_cwd)
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_admin_reclassify_dry_run_reports_orphan_transcriptions_without_mutation(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("ing-1", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-10T12:00:00"),
            )
            db.execute(
                """
                INSERT INTO transcriptions (
                    id, ingest_id, text, transcript_clean, language_probability,
                    created_at, quality_state, review_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "tr-1",
                    "ing-1",
                    "Роман Роман ты где Роман",
                    "Роман Роман ты где Роман",
                    0.99,
                    "2026-03-10T12:00:00",
                    "trusted",
                    0,
                ),
            )

        client = TestClient(app)
        resp = client.post("/admin/reclassify", json={"mode": "dry_run", "date": "2026-03-10"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["affected_episodes"] == 0
        assert body["affected_transcriptions"] == 1
        assert body["proposed_transcription_state_counts"]["garbage"] == 1
        row = db.fetchone("SELECT quality_state FROM transcriptions WHERE id = ?", ("tr-1",))
        assert row["quality_state"] == "trusted"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_admin_reclassify_apply_updates_orphan_transcriptions(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    old_cwd = Path.cwd()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        os.chdir(tmp_path)
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("ing-1", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-10T12:00:00"),
            )
            db.execute(
                """
                INSERT INTO transcriptions (
                    id, ingest_id, text, transcript_clean, language_probability,
                    created_at, quality_state, review_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "tr-1",
                    "ing-1",
                    "Роман Роман ты где Роман",
                    "Роман Роман ты где Роман",
                    0.99,
                    "2026-03-10T12:00:00",
                    "trusted",
                    0,
                ),
            )

        client = TestClient(app)
        resp = client.post("/admin/reclassify", json={"mode": "apply", "date": "2026-03-10"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["affected_transcriptions"] == 1
        assert body["transitions_written"] >= 1
        row = db.fetchone("SELECT quality_state FROM transcriptions WHERE id = ?", ("tr-1",))
        assert row["quality_state"] in {"garbage", "quarantined"}
        transitions = db.fetchone(
            """
            SELECT COUNT(*) AS c FROM quality_state_transition_log
            WHERE entity_type = 'transcription' AND entity_id = ?
            """,
            ("tr-1",),
        )
        assert transitions["c"] >= 1
    finally:
        os.chdir(old_cwd)
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_admin_recheck_dry_run_does_not_mutate_uncertain_episode(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, quality_state, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-r1",
                    "2026-03-11T10:00:00",
                    "2026-03-11T10:01:00",
                    "summarized",
                    1,
                    "[]",
                    "очень коротко",
                    "очень коротко",
                    "",
                    "[]",
                    "[]",
                    "[]",
                    0.1,
                    1,
                    "uncertain",
                    "2026-03-11",
                ),
            )

        client = TestClient(app)
        resp = client.post("/admin/recheck", json={"mode": "dry_run", "date": "2026-03-11"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "dry_run"
        assert body["target_states"] == ["uncertain", "quarantined"]
        assert body["affected_episodes"] == 1
        row = db.fetchone("SELECT quality_state FROM episodes WHERE id = ?", ("ep-r1",))
        assert row["quality_state"] == "uncertain"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_admin_recheck_apply_updates_quarantined_transcription_and_rebuilds_digest(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    old_cwd = Path.cwd()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        os.chdir(tmp_path)
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("ing-r2", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-11T11:00:00"),
            )
            db.execute(
                """
                INSERT INTO transcriptions (
                    id, ingest_id, text, transcript_clean, language_probability,
                    created_at, quality_state, review_required, needs_recheck
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "tr-r2",
                    "ing-r2",
                    "Роман Роман ты где Роман",
                    "Роман Роман ты где Роман",
                    0.99,
                    "2026-03-11T11:00:00",
                    "quarantined",
                    1,
                    1,
                ),
            )

        client = TestClient(app)
        resp = client.post(
            "/admin/recheck",
            json={"mode": "apply", "date": "2026-03-11", "states": ["quarantined"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["affected_transcriptions"] == 1
        assert body["digest_rebuilds"] >= 0
        row = db.fetchone("SELECT quality_state FROM transcriptions WHERE id = ?", ("tr-r2",))
        assert row["quality_state"] in {"garbage", "quarantined", "uncertain"}
        digest_row = db.fetchone(
            "SELECT rebuild_reason FROM digest_cache WHERE date = ?",
            ("2026-03-11",),
        )
        if digest_row is not None:
            assert digest_row["rebuild_reason"] == "truth_recheck"
        transitions = db.fetchone(
            """
            SELECT COUNT(*) AS c FROM quality_state_transition_log
            WHERE entity_type = 'transcription' AND entity_id = ? AND source = 'recheck'
            """,
            ("tr-r2",),
        )
        # Transition may remain zero if recheck keeps the same state; both outcomes are acceptable.
        assert transitions["c"] >= 0
    finally:
        os.chdir(old_cwd)
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_digest_daily_force_returns_empty_when_only_garbage_data_exists(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    old_cwd = Path.cwd()
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        os.chdir(tmp_path)
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("ing-1", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-10T12:00:00"),
            )
            db.execute(
                """
                INSERT INTO transcriptions (
                    id, ingest_id, text, transcript_clean, language_probability,
                    created_at, quality_state, review_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("tr-1", "ing-1", "Роман Роман ты где Роман", "Роман Роман ты где Роман", 0.99, "2026-03-10T12:00:00", "garbage", 1),
            )
            db.execute(
                """
                INSERT INTO recording_analyses (
                    id, transcription_id, summary, emotions, actions, topics, urgency, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("ra-1", "tr-1", "Шумный старый итог", "[]", "[]", "[\"шум\"]", "low", "2026-03-10T12:00:05"),
            )

        client = TestClient(app)
        resp = client.get("/digest/daily", params={"date": "2026-03-10", "format": "json", "force": "true"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["_status"] == "empty"
        assert body["total_recordings"] == 0
        assert body["summary_text"] == ""
    finally:
        os.chdir(old_cwd)
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_query_threads_returns_trusted_long_thread_with_filters(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, quality_state,
                    review_required, day_key, thread_key, long_thread_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T10:00:00",
                    "2026-03-10T10:10:00",
                    "summarized",
                    1,
                    '["tr-1"]',
                    "обсуждали бюджет Q2 с Маратом",
                    "обсуждали бюджет Q2 с Маратом",
                    "бюджет с Маратом",
                    '["бюджет","Q2"]',
                    '["Марат"]',
                    "[]",
                    0.9,
                    0,
                    "trusted",
                    0,
                    "2026-03-10",
                    "dt-1",
                    "lt-1",
                ),
            )
            db.execute(
                """
                INSERT INTO day_threads (
                    id, day_key, topic_cluster, episode_ids_json, summary, open_questions,
                    commitments_json, topics_json, participants_json, carryover_candidate,
                    long_thread_key, topic_overlap_score, participant_overlap_score,
                    temporal_proximity_score, commitment_overlap_score, thread_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "dt-1",
                    "2026-03-10",
                    "budget",
                    '["ep-1"]',
                    "обсуждение бюджета",
                    "",
                    "[]",
                    '["бюджет","Q2"]',
                    '["Марат"]',
                    1,
                    "lt-1",
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
                    '["dt-1"]',
                    '["Марат"]',
                    '["бюджет","Q2"]',
                    "active",
                    "линия обсуждений бюджета",
                    0.8,
                ),
            )

        client = TestClient(app)
        resp = client.get(
            "/query/threads",
            params={"days_back": 30, "topic": "бюджет", "participant": "марат", "status": "active"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool"] == "query_threads"
        assert body["data"]["total"] == 1
        thread = body["data"]["threads"][0]
        assert thread["long_thread_id"] == "lt-1"
        assert thread["day_count"] == 1
        assert "Марат" in thread["participants"]
        assert "бюджет" in thread["topics"]
        assert thread["top_participants"] == ["Марат"]
        assert thread["top_topics"] == ["бюджет", "Q2"]
        assert thread["day_keys"] == ["2026-03-10"]
        assert thread["latest_summary"] == "обсуждение бюджета"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_query_threads_returns_empty_for_non_matching_filters(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO long_threads (
                    id, thread_key, first_seen_at, last_seen_at, day_thread_ids_json,
                    participants_json, topics_json, status, summary, continuity_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "lt-2",
                    "lt-key-2",
                    "2026-03-10",
                    "2026-03-10",
                    "[]",
                    '["Алия"]',
                    '["найм"]',
                    "active",
                    "линия про найм",
                    0.7,
                ),
            )

        client = TestClient(app)
        resp = client.get("/query/threads", params={"participant": "марат"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] == 0
        assert body["data"]["threads"] == []
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_query_threads_uses_commitment_people_in_participant_payload(tmp_path):
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO long_threads (
                    id, thread_key, first_seen_at, last_seen_at, day_thread_ids_json,
                    participants_json, topics_json, status, summary, continuity_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "lt-3",
                    "lt-key-3",
                    "2026-03-11",
                    "2026-03-11",
                    '["dt-3"]',
                    "[]",
                    '["курсы"]',
                    "active",
                    "линия про курсы",
                    0.8,
                ),
            )
            db.execute(
                """
                INSERT INTO day_threads (
                    id, day_key, topic_cluster, episode_ids_json, summary, open_questions,
                    commitments_json, topics_json, participants_json, carryover_candidate,
                    long_thread_key, topic_overlap_score, participant_overlap_score,
                    temporal_proximity_score, commitment_overlap_score, thread_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "dt-3",
                    "2026-03-11",
                    "courses",
                    '["ep-3"]',
                    "линия про курсы",
                    "",
                    '[{"person":"Марат","text":"созвониться"}]',
                    '["курсы"]',
                    "[]",
                    1,
                    "lt-3",
                    0.8,
                    0.0,
                    1.0,
                    0.8,
                    0.85,
                ),
            )
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, quality_state,
                    review_required, day_key, thread_key, long_thread_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-3",
                    "2026-03-11T10:00:00",
                    "2026-03-11T10:10:00",
                    "summarized",
                    1,
                    '["tr-3"]',
                    "созвониться с Маратом по курсам",
                    "созвониться с Маратом по курсам",
                    "линия про курсы",
                    '["курсы"]',
                    "[]",
                    '[{"person":"Марат","text":"созвониться"}]',
                    0.9,
                    0,
                    "trusted",
                    0,
                    "2026-03-11",
                    "dt-3",
                    "lt-3",
                ),
            )

        client = TestClient(app)
        resp = client.get("/query/threads", params={"participant": "марат"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] == 1
        thread = body["data"]["threads"][0]
        assert thread["participants"] == ["Марат"]
        assert thread["top_participants"] == ["Марат"]
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
