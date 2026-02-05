"""Тесты API endpoints."""
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from src.api.main import app


def test_ingest_audio():
    """Проверяет загрузку аудио."""
    client = TestClient(app)
    
    # Создаём временный WAV файл для теста
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        # Записываем минимальный WAV заголовок (44 байта) + немного данных
        wav_header = bytes([
            0x52, 0x49, 0x46, 0x46,  # "RIFF"
            0x24, 0x00, 0x00, 0x00,  # chunk size
            0x57, 0x41, 0x56, 0x45,  # "WAVE"
            0x66, 0x6D, 0x74, 0x20,  # "fmt "
            0x10, 0x00, 0x00, 0x00,  # fmt chunk size
            0x01, 0x00,              # audio format (PCM)
            0x01, 0x00,              # channels (mono)
            0x44, 0xAC, 0x00, 0x00,  # sample rate (44100)
            0x88, 0x58, 0x01, 0x00,  # byte rate
            0x02, 0x00,              # block align
            0x10, 0x00,              # bits per sample (16)
            0x64, 0x61, 0x74, 0x61,  # "data"
            0x00, 0x00, 0x00, 0x00,  # data chunk size
        ])
        tmp.write(wav_header)
        tmp_path = Path(tmp.name)
    
    try:
        # Отправляем файл
        with open(tmp_path, "rb") as f:
            files = {"file": ("test.wav", f, "audio/wav")}
            resp = client.post("/ingest/audio", files=files)
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert "id" in data
        assert "filename" in data
        assert "path" in data
        assert data["size"] > 0
    finally:
        # Удаляем временный файл
        tmp_path.unlink()


def test_ingest_status():
    """Проверяет endpoint статуса."""
    client = TestClient(app)
    
    # Проверяем статус несуществующего файла (в MVP всегда pending)
    resp = client.get("/ingest/status/test-id-123")
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-id-123"
    assert data["status"] == "pending"

