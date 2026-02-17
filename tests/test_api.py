"""Тесты API endpoints."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.api.main import app
from src.utils.config import settings


def test_ingest_audio(tmp_path):
    """Проверяет загрузку аудио."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    wav_header = bytes([
        0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00,
        0x57, 0x41, 0x56, 0x45, 0x66, 0x6D, 0x74, 0x20,
        0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
        0x44, 0xAC, 0x00, 0x00, 0x88, 0x58, 0x01, 0x00,
        0x02, 0x00, 0x10, 0x00, 0x64, 0x61, 0x74, 0x61,
        0x00, 0x00, 0x00, 0x00,
    ])
    # Патчим только UPLOADS_PATH (тот же объект settings, что и в main)
    with patch.object(settings, "UPLOADS_PATH", tmp_path):
        client = TestClient(app)
        files = {"file": ("test.wav", wav_header, "audio/wav")}
        resp = client.post("/ingest/audio", files=files)
    assert resp.status_code == 200, (resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text)
    data = resp.json()
    assert data["status"] == "received"
    assert "id" in data
    assert "filename" in data
    assert "path" in data
    assert data["size"] > 0


def test_ingest_status():
    """Проверяет endpoint статуса."""
    client = TestClient(app)
    
    # Проверяем статус несуществующего файла (в MVP всегда pending)
    resp = client.get("/ingest/status/test-id-123")
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-id-123"
    assert data["status"] == "pending"

