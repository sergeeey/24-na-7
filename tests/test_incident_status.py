from fastapi.testclient import TestClient
from datetime import date

from src.api.main import app
from src.utils.incidents import validate_incident_ledger


def test_incident_ledger_validator_rejects_closed_without_guard_or_signpost():
    payload = {
        "incidents": [
            {
                "incident_id": "INC-001",
                "signature": "demo_signature",
                "title": "demo",
                "symptoms": ["symptom"],
                "root_cause": "real cause",
                "evidence": ["log line"],
                "what_worked": "",
                "what_failed": "",
                "guardrail": "",
                "regression_test": "(добавить)",
                "signpost": "",
                "owner": "",
                "status": "closed",
            }
        ]
    }

    errors = validate_incident_ledger(payload)

    assert any("signpost must be filled" in error for error in errors)
    assert any("requires guardrail or regression_test" in error for error in errors)


def test_incident_status_exposes_runtime_signals(tmp_path):
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
            db.execute(
                """
                INSERT INTO ingest_queue (
                    id, segment_id, filename, file_path, file_size, status,
                    transport_status, processing_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "stale-received",
                    "seg-stale",
                    "stale.wav",
                    "/tmp/stale.wav",
                    900,
                    "received",
                    "server_acked",
                    "received",
                    "2026-03-10T10:00:00",
                ),
            )
            db.execute(
                """
                INSERT INTO ingest_queue (
                    id, segment_id, filename, file_path, file_size, status,
                    transport_status, processing_status, created_at, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ready-no-enrichment",
                    "seg-ready",
                        "ready.wav",
                        "/tmp/ready.wav",
                        2048,
                        "event_ready",
                        "server_acked",
                        "event_ready",
                        f"{today}T10:00:00+00:00",
                        f"{today}T10:01:00+00:00",
                    ),
                )
            db.execute(
                """
                INSERT INTO transcriptions (
                    id, ingest_id, text, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                    (
                        "tr-ready",
                        "ready-no-enrichment",
                        "text",
                        f"{today}T10:00:30+00:00",
                    ),
                )
            db.execute(
                """
                INSERT INTO ingest_queue (
                    id, segment_id, filename, file_path, file_size, status,
                    transport_status, processing_status, created_at, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "micro-wav",
                    "seg-micro",
                        "micro.wav",
                        "/tmp/micro.wav",
                        44,
                        "filtered",
                        "server_acked",
                        "filtered",
                        f"{today}T11:00:00+00:00",
                        f"{today}T11:00:10+00:00",
                    ),
                )
            db.execute(
                """
                INSERT INTO ingest_queue (
                    id, segment_id, filename, file_path, file_size, status,
                    transport_status, processing_status, created_at, processed_at, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "noise-filtered",
                    "seg-noise",
                    "noise.wav",
                    "/tmp/noise.wav",
                    2048,
                    "filtered",
                    "server_acked",
                    "filtered",
                    f"{today}T11:10:00+00:00",
                    f"{today}T11:10:10+00:00",
                    "noise",
                ),
            )

        ledger_payload = {
            "incidents": [
                {
                    "incident_id": "INC-001",
                    "signature": "android_debug_falls_back_to_remote_when_local_alive",
                    "title": "debug fallback",
                    "symptoms": ["symptom"],
                    "root_cause": "(уточнить)",
                    "evidence": ["log"],
                    "what_worked": "",
                    "what_failed": "",
                    "guardrail": "",
                    "regression_test": "",
                    "signpost": "check logcat",
                    "owner": "",
                    "status": "open",
                },
                {
                    "incident_id": "INC-002",
                    "signature": "ingest_stuck_received_without_transcription",
                    "title": "stuck received",
                    "symptoms": ["symptom"],
                    "root_cause": "(уточнить)",
                    "evidence": ["db"],
                    "what_worked": "",
                    "what_failed": "",
                    "guardrail": "",
                    "regression_test": "",
                    "signpost": "stale_received",
                    "owner": "",
                    "status": "open",
                },
                {
                    "incident_id": "INC-003",
                    "signature": "enrichment_404_after_segment_complete",
                    "title": "missing enrichment",
                    "symptoms": ["symptom"],
                    "root_cause": "(уточнить)",
                    "evidence": ["db"],
                    "what_worked": "",
                    "what_failed": "",
                    "guardrail": "",
                    "regression_test": "",
                    "signpost": "missing structured_event",
                    "owner": "",
                    "status": "open",
                },
                {
                    "incident_id": "INC-004",
                    "signature": "micro_wav_segments_under_min_size",
                    "title": "micro wav",
                    "symptoms": ["symptom"],
                    "root_cause": "(уточнить)",
                    "evidence": ["db"],
                    "what_worked": "",
                    "what_failed": "",
                    "guardrail": "",
                    "regression_test": "",
                    "signpost": "file_size <= 512",
                    "owner": "",
                    "status": "open",
                },
                {
                    "incident_id": "INC-005",
                    "signature": "unsupported_language_unknown_filters_valid_ru_audio",
                    "title": "unknown lang",
                    "symptoms": ["symptom"],
                    "root_cause": "(уточнить)",
                    "evidence": ["db"],
                    "what_worked": "",
                    "what_failed": "",
                    "guardrail": "",
                    "regression_test": "",
                    "signpost": "unsupported_language",
                    "owner": "",
                    "status": "open",
                },
                {
                    "incident_id": "INC-006",
                    "signature": "vad_noise_filtering_overrejects_valid_short_speech",
                    "title": "noise filtered speech",
                    "symptoms": ["symptom"],
                    "root_cause": "(уточнить)",
                    "evidence": ["db"],
                    "what_worked": "",
                    "what_failed": "",
                    "guardrail": "",
                    "regression_test": "",
                    "signpost": "filtered noise rate",
                    "owner": "",
                    "status": "open",
                },
            ]
        }

        client = TestClient(app)
        from unittest.mock import patch

        with patch("src.api.routers.ingest.load_incident_ledger", return_value=ledger_payload):
            signpost = client.post(
                "/ingest/client-signpost",
                json={
                    "source": "android-service",
                    "route_kind": "background_ws",
                    "primary_url": "ws://localhost:8000",
                    "resolved_url": "wss://reflexio247.duckdns.org/ws/ingest",
                    "decision": "fallback_remote",
                    "is_local_primary": True,
                    "debug_build": True,
                },
            )
            assert signpost.status_code == 200
            response = client.get("/ingest/incident-status")

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["total"] == 6
        assert payload["summary"]["alerting"] == 5
        assert payload["summary"]["unknown"] == 0

        signal_by_signature = {
            item["signature"]: item["signal"] for item in payload["incidents"]
        }
        assert signal_by_signature["android_debug_falls_back_to_remote_when_local_alive"]["state"] == "alert"
        assert signal_by_signature["android_debug_falls_back_to_remote_when_local_alive"]["value"] == 1
        assert signal_by_signature["ingest_stuck_received_without_transcription"]["state"] == "alert"
        assert signal_by_signature["ingest_stuck_received_without_transcription"]["value"] == 1
        assert signal_by_signature["enrichment_404_after_segment_complete"]["state"] == "alert"
        assert signal_by_signature["enrichment_404_after_segment_complete"]["value"] == 1
        assert signal_by_signature["micro_wav_segments_under_min_size"]["state"] == "alert"
        assert signal_by_signature["micro_wav_segments_under_min_size"]["value"] == 1
        assert signal_by_signature["unsupported_language_unknown_filters_valid_ru_audio"]["state"] == "ok"
        assert signal_by_signature["vad_noise_filtering_overrejects_valid_short_speech"]["state"] == "alert"
        assert signal_by_signature["vad_noise_filtering_overrejects_valid_short_speech"]["value"] == 1
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
