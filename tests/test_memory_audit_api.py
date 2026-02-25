"""Tests for memory retrieval and audit integrity endpoints."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.memory.semantic_memory import consolidate_to_memory_node, ensure_semantic_memory_tables
from src.storage.integrity import append_integrity_event, ensure_integrity_tables
from src.utils.config import settings


def test_memory_retrieve_endpoint(tmp_path):
    db_root = tmp_path / "storage"
    db_root.mkdir(parents=True, exist_ok=True)
    db_path = db_root / "reflexio.db"

    ensure_semantic_memory_tables(db_path)
    consolidate_to_memory_node(
        db_path=db_path,
        ingest_id="ingest-1",
        transcription_id="tx-1",
        text="Обсуждение бюджета проекта и дедлайнов команды",
        summary="Планирование бюджета",
        topics=["бюджет", "планирование"],
    )

    with patch.object(settings, "STORAGE_PATH", db_root), patch.object(settings, "RETRIEVAL_ENABLED", True):
        client = TestClient(app)
        resp = client.get("/memory/retrieve", params={"q": "бюджет", "top_k": 5})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["count"] >= 1
    assert payload["matches"][0]["source_ingest_id"] == "ingest-1"


def test_audit_ingest_endpoint_chain_valid(tmp_path):
    db_root = tmp_path / "storage"
    db_root.mkdir(parents=True, exist_ok=True)
    db_path = db_root / "reflexio.db"

    ensure_integrity_tables(db_path)
    append_integrity_event(db_path, "ingest-2", "received", payload_bytes=b"abc")
    append_integrity_event(db_path, "ingest-2", "transcribed", payload_text="hello")

    with patch.object(settings, "STORAGE_PATH", db_root), patch.object(settings, "INTEGRITY_CHAIN_ENABLED", True):
        client = TestClient(app)
        resp = client.get("/audit/ingest/ingest-2")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["events_count"] == 2
    assert payload["chain_valid"] is True
