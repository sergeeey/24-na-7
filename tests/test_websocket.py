"""Tests for WebSocket /ws/ingest endpoint."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.api.main import app


def test_websocket_ingest_accept_and_receive_binary():
    """WebSocket /ws/ingest accepts connection and responds to binary WAV."""
    client = TestClient(app)
    with patch("src.api.main.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {"text": "hello", "language": "en"}
        with client.websocket_connect("/ws/ingest") as websocket:
            websocket.send_bytes(b"fake-wav-bytes")
            msg = websocket.receive_json()
            assert msg["type"] == "received"
            assert "file_id" in msg
            assert msg["status"] == "queued"
            msg2 = websocket.receive_json()
            assert msg2["type"] == "transcription"
            assert msg2.get("text") == "hello"


def test_websocket_ingest_json_audio():
    """WebSocket /ws/ingest accepts JSON with type audio and base64 data."""
    import base64
    client = TestClient(app)
    with patch("src.api.main.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {"text": "test", "language": "en"}
        with client.websocket_connect("/ws/ingest") as websocket:
            websocket.send_text('{"type": "audio", "data": "' + base64.b64encode(b"wav").decode() + '"}')
            msg = websocket.receive_json()
            assert msg["type"] == "received"
            assert "file_id" in msg
            msg2 = websocket.receive_json()
            assert msg2["type"] == "transcription"
            assert msg2.get("text") == "test"


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
    """WebSocket /ws/ingest accepts invalid/non-WAV binary, returns received then error from transcribe."""
    client = TestClient(app)
    with patch("src.api.main.transcribe_audio") as mock_transcribe:
        mock_transcribe.side_effect = ValueError("Invalid WAV or unsupported format")
        with client.websocket_connect("/ws/ingest") as websocket:
            websocket.send_bytes(b"not-wav-content")
            msg = websocket.receive_json()
            assert msg["type"] == "received"
            assert "file_id" in msg
            msg2 = websocket.receive_json()
            assert msg2["type"] == "error"
            assert "file_id" in msg2 or "message" in msg2
