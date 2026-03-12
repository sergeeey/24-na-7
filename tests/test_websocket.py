"""Tests for WebSocket /ws/ingest endpoint."""
import asyncio
import base64
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
import wave

from fastapi.testclient import TestClient
from src.api.main import app
from src.api.routers.websocket import _result_reader, websocket_ingest


def _valid_wav_bytes() -> bytes:
    """Build a minimal valid WAV payload for tests."""
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


def _mock_worker_that_emits_transcription(registry, text: str):
    """Возвращает мок IngestWorker, который сразу кладёт результат в очередь соединения."""
    def submit(task):
        q = registry.get(task.connection_id)
        if q:
            q.put_nowait({"type": "transcription", "text": text, "language": "en"})

    worker = MagicMock()
    worker.submit = submit
    return worker


def test_websocket_ingest_accept_and_receive_binary():
    """WebSocket /ws/ingest accepts connection and responds to binary WAV."""
    client = TestClient(app)
    with patch("src.api.routers.websocket.get_ingest_worker") as m:
        m.side_effect = lambda registry: _mock_worker_that_emits_transcription(
            registry, "hello team meeting"
        )
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
    with patch("src.api.routers.websocket.get_ingest_worker") as m:
        m.side_effect = lambda registry: _mock_worker_that_emits_transcription(
            registry, "test project update"
        )
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


def test_websocket_ingest_deduplicates_same_segment_id(tmp_path):
    """Same segment_id should be accepted once and then treated as duplicate."""
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    uploads_path = storage_path / "uploads"
    storage_path.mkdir()
    uploads_path.mkdir()

    old_storage = settings.STORAGE_PATH
    old_uploads = settings.UPLOADS_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)
    object.__setattr__(settings, "UPLOADS_PATH", uploads_path)

    client = TestClient(app)
    worker = MagicMock()
    worker.submit = MagicMock()

    try:
        with patch("src.api.routers.websocket.get_ingest_worker", return_value=worker):
            with client.websocket_connect("/ws/ingest") as websocket:
                payload = base64.b64encode(_valid_wav_bytes()).decode()
                body = (
                    '{"type":"audio","segment_id":"seg-123","captured_at":"2026-03-10T12:00:00Z","data":"'
                    + payload
                    + '"}'
                )
                websocket.send_text(body)
                first = websocket.receive_json()
                assert first["type"] == "received"
                assert first["status"] == "queued"

                websocket.send_text(body)
                second = websocket.receive_json()
                assert second["type"] == "received"
                assert second["status"] == "duplicate"
                assert second["file_id"] == first["file_id"]

        assert worker.submit.call_count == 1
        saved = list(Path(uploads_path).glob("*.wav"))
        assert len(saved) == 1
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
        object.__setattr__(settings, "UPLOADS_PATH", old_uploads)


def test_result_reader_stops_cleanly_after_disconnect_error():
    """Reader should exit quietly when the socket is already closed."""

    class FakeWebSocket:
        async def send_json(self, _msg):
            raise RuntimeError('Cannot call "send" once a disconnect message has been received.')

    async def runner():
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        await queue.put({"type": "transcription", "text": "hello"})
        await _result_reader(FakeWebSocket(), "conn-1", queue)

    asyncio.run(runner())


def test_websocket_ingest_stops_on_disconnect_message():
    """Main receive loop must stop after websocket.disconnect instead of calling receive again."""

    class FakeClient:
        host = "127.0.0.1"
        port = 12345

    class FakeWebSocket:
        def __init__(self):
            self.client = FakeClient()
            self.headers = {"authorization": "Bearer test-api-key"}
            self.query_params = {}
            self.accepted = False
            self.receive_calls = 0

        async def accept(self):
            self.accepted = True

        async def receive(self):
            self.receive_calls += 1
            if self.receive_calls == 1:
                return {"type": "websocket.disconnect", "code": 1000}
            raise AssertionError("receive() called after disconnect")

        async def send_json(self, _msg):
            raise AssertionError("send_json() should not be called after disconnect")

    async def runner():
        websocket = FakeWebSocket()
        with patch("src.api.routers.websocket.verify_websocket_token", return_value=True):
            await websocket_ingest(websocket)
            assert websocket.accepted is True
            assert websocket.receive_calls == 1

    asyncio.run(runner())
