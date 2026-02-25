"""Tests for WebSocket /ws/ingest endpoint."""
import base64
from io import BytesIO
from unittest.mock import patch
import wave

from fastapi.testclient import TestClient
from src.api.main import app


def _valid_wav_bytes() -> bytes:
    """Build a minimal valid WAV payload for tests."""
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


def test_websocket_ingest_accept_and_receive_binary():
    """WebSocket /ws/ingest accepts connection and responds to binary WAV."""
    client = TestClient(app)
    with patch("src.api.routers.websocket.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {"text": "hello team meeting", "language": "en"}
        with client.websocket_connect("/ws/ingest") as websocket:
            websocket.send_bytes(_valid_wav_bytes())
            msg = websocket.receive_json()
            assert msg["type"] == "received"
            assert "file_id" in msg
            assert msg["status"] == "queued"
            msg2 = websocket.receive_json()
            assert msg2["type"] == "transcription"
            assert msg2.get("text") == "hello team meeting"


def test_websocket_ingest_json_audio():
    """WebSocket /ws/ingest accepts JSON with type audio and base64 data."""
    client = TestClient(app)
    with patch("src.api.routers.websocket.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {"text": "test project update", "language": "en"}
        with client.websocket_connect("/ws/ingest") as websocket:
            payload = base64.b64encode(_valid_wav_bytes()).decode()
            websocket.send_text('{"type": "audio", "data": "' + payload + '"}')
            msg = websocket.receive_json()
            assert msg["type"] == "received"
            assert "file_id" in msg
            msg2 = websocket.receive_json()
            assert msg2["type"] == "transcription"
            assert msg2.get("text") == "test project update"


def test_websocket_ingest_unknown_type():
    """WebSocket /ws/ingest returns error for unknown message type."""
    client = TestClient(app)
    with client.websocket_connect("/ws/ingest") as websocket:
        websocket.send_text('{"type": "unknown"}')
        msg = websocket.receive_json()
        assert msg["type"] == "error"
        assert "message" in msg


def test_websocket_ingest_empty_binary():
    """WebSocket /ws/ingest returns error for empty binary body (no crash)."""
    client = TestClient(app)
    with client.websocket_connect("/ws/ingest") as websocket:
        websocket.send_bytes(b"")
        msg = websocket.receive_json()
        assert msg["type"] == "error"
        assert "message" in msg
        assert "empty" in msg["message"].lower() or "Empty" in msg["message"]


def test_websocket_ingest_invalid_audio_binary():
    """WebSocket /ws/ingest returns immediate validation error for invalid/non-WAV binary."""
    client = TestClient(app)
    with client.websocket_connect("/ws/ingest") as websocket:
        websocket.send_bytes(b"not-wav-content")
        msg = websocket.receive_json()
        assert msg["type"] == "error"
        assert "message" in msg
        # ПОЧЕМУ: после H1-фикса (security) сервер не раскрывает внутренние детали ошибок.
        # Проверяем только что ответ — это error с непустым message.
        assert len(msg["message"]) > 0
