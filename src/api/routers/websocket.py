"""Роутер для WebSocket endpoints."""
import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.middleware.auth_middleware import verify_websocket_token
from src.api.middleware.safe_middleware import get_safe_checker
from src.core.audio_processing import create_ingest_artifact
from src.ingest.worker import IngestTask, get_ingest_worker
from src.utils.logging import get_logger

logger = get_logger("api.websocket")
router = APIRouter(tags=["websocket"])

# Реестр соединений: connection_id -> Queue для доставки результатов фоновой обработки.
_ingest_result_registry: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}


def get_ingest_result_registry() -> dict[str, asyncio.Queue[dict[str, Any] | None]]:
    """Реестр для доставки результатов IngestWorker в WebSocket. Передаётся в get_ingest_worker при старте."""
    return _ingest_result_registry

class _ConnectionState:
    """Кэш последней транскрипции per WebSocket connection.

    ПОЧЕМУ класс: инкапсулирует state + behavior вместо голого dict + 3 функций.
    Не нуждается в threading.Lock — WebSocket handlers работают в asyncio event loop
    (single-threaded cooperative multitasking).
    """

    MERGE_WINDOW_SECONDS = 5

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    def recent_text(self, connection_id: str) -> str:
        now = datetime.now(timezone.utc)
        prev = self._cache.get(connection_id)
        if not prev:
            return ""
        dt = (now - prev["ts"]).total_seconds()
        if dt <= self.MERGE_WINDOW_SECONDS and prev.get("text"):
            return str(prev["text"])
        return ""

    def remember(self, connection_id: str, text: str) -> None:
        self._cache[connection_id] = {
            "ts": datetime.now(timezone.utc),
            "text": text,
        }

    def disconnect(self, connection_id: str) -> None:
        self._cache.pop(connection_id, None)


_conn_state = _ConnectionState()


def _is_disconnect_message(message: dict[str, Any]) -> bool:
    """Starlette signals closed sockets via websocket.disconnect frames."""
    return message.get("type") == "websocket.disconnect"


def _is_closed_socket_error(exc: Exception) -> bool:
    """Treat post-disconnect send/receive errors as normal connection shutdown."""
    error_text = str(exc).lower()
    return "disconnect message has been received" in error_text or "websocket is not connected" in error_text


async def _result_reader(
    websocket: WebSocket,
    connection_id: str,
    queue: asyncio.Queue[dict[str, Any] | None],
) -> None:
    """Читает результаты из очереди и отправляет клиенту. Выход по None (shutdown)."""
    while True:
        msg = await queue.get()
        if msg is None:
            break
        try:
            await websocket.send_json(msg)
            if msg.get("type") == "transcription" and msg.get("text"):
                _conn_state.remember(connection_id, msg.get("text", ""))
        except Exception as e:
            if _is_closed_socket_error(e):
                logger.info("result_reader_disconnected", connection_id=connection_id)
                break
            logger.warning("result_reader_send_failed", connection_id=connection_id, error=str(e))
            break


def _enqueue_audio_segment(
    audio_bytes: bytes,
    file_id: str,
    connection_id: str,
    *,
    segment_id: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Сохранить артефакт (WAV + ingest_queue), поставить задачу в IngestWorker. «received» шлёт вызывающий."""
    artifact = create_ingest_artifact(
        content=audio_bytes,
        content_type="audio/wav",
        original_filename=f"{file_id}.wav",
        stage="ws_audio_received",
        file_id=file_id,
        segment_id=segment_id,
        captured_at=captured_at,
        queue_status="received",
    )
    if artifact.get("duplicate"):
        return artifact
    dest_path: Path = artifact["dest_path"]
    enrichment_prefix = _conn_state.recent_text(connection_id)
    worker = get_ingest_worker(get_ingest_result_registry())
    worker.submit(
        IngestTask(
            ingest_id=file_id,
            file_path=dest_path,
            connection_id=connection_id,
            enrichment_prefix=enrichment_prefix or None,
        )
    )
    return artifact


@router.websocket("/ws/ingest")
async def websocket_ingest(websocket: WebSocket):
    """WebSocket для приёма аудио-сегментов. Принял байты → сразу «received» → обработка в фоне → результат в очередь соединения."""
    if not verify_websocket_token(websocket):
        logger.warning("websocket_auth_failed", client=websocket.client)
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    connection_id = str(id(websocket))
    result_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    _ingest_result_registry[connection_id] = result_queue
    reader_task = asyncio.create_task(_result_reader(websocket, connection_id, result_queue))
    logger.info("websocket_ingest_connected", client=websocket.client)
    try:
        while True:
            data = await websocket.receive()
            if _is_disconnect_message(data):
                break
            if "bytes" in data:
                if not data["bytes"]:
                    await websocket.send_json({"type": "error", "message": "Empty audio"})
                    continue
                safe = get_safe_checker()
                if safe and len(data["bytes"]) > safe.MAX_FILE_SIZE_BYTES:
                    await websocket.send_json({"type": "error", "message": "File too large"})
                    continue
                file_id = str(uuid.uuid4())
                try:
                    artifact = _enqueue_audio_segment(data["bytes"], file_id, connection_id)
                except Exception as e:
                    logger.warning("ingest_artifact_failed", file_id=file_id, error=str(e))
                    await websocket.send_json({"type": "error", "file_id": file_id, "message": "Failed to save audio"})
                    continue
                await websocket.send_json(
                    {
                        "type": "received",
                        "file_id": artifact["ingest_id"],
                        "status": "duplicate" if artifact.get("duplicate") else "queued",
                    }
                )
                existing_result = artifact.get("existing_result")
                if artifact.get("duplicate") and existing_result:
                    await websocket.send_json(
                        {
                            "type": "transcription",
                            "file_id": artifact["ingest_id"],
                            "text": existing_result.get("text", ""),
                            "language": existing_result.get("language", ""),
                        }
                    )
            elif "text" in data and data["text"]:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "audio" and msg.get("data"):
                        audio_bytes = base64.b64decode(msg["data"])
                        safe = get_safe_checker()
                        if safe and len(audio_bytes) > safe.MAX_FILE_SIZE_BYTES:
                            await websocket.send_json({"type": "error", "message": "File too large"})
                            continue
                        file_id = str(uuid.uuid4())
                        segment_id = msg.get("segment_id")
                        captured_at = msg.get("captured_at")
                        if captured_at is not None:
                            captured_at = str(captured_at)
                        try:
                            artifact = _enqueue_audio_segment(
                                audio_bytes,
                                file_id,
                                connection_id,
                                segment_id=segment_id,
                                captured_at=captured_at,
                            )
                        except Exception as e:
                            logger.warning("ingest_artifact_failed", file_id=file_id, error=str(e))
                            await websocket.send_json({"type": "error", "file_id": file_id, "message": "Failed to save audio"})
                            continue
                        await websocket.send_json(
                            {
                                "type": "received",
                                "file_id": artifact["ingest_id"],
                                "status": "duplicate" if artifact.get("duplicate") else "queued",
                            }
                        )
                        existing_result = artifact.get("existing_result")
                        if artifact.get("duplicate") and existing_result:
                            await websocket.send_json(
                                {
                                    "type": "transcription",
                                    "file_id": artifact["ingest_id"],
                                    "text": existing_result.get("text", ""),
                                    "language": existing_result.get("language", ""),
                                }
                            )
                    else:
                        await websocket.send_json({"type": "error", "message": "Unknown message type"})
                except (json.JSONDecodeError, KeyError) as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        logger.info("websocket_ingest_disconnected", client=websocket.client)
    except Exception as e:
        logger.error("websocket_ingest_error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
    finally:
        _ingest_result_registry.pop(connection_id, None)
        try:
            result_queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
        _conn_state.disconnect(connection_id)
