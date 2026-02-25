"""Тесты API endpoints."""
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.utils.config import settings


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


def test_ingest_status():
    """Проверяет endpoint статуса."""
    client = TestClient(app)

    resp = client.get("/ingest/status/test-id-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-id-123"
    assert data["status"] == "pending"
