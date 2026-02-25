"""Роутер для WebSocket endpoints."""
import base64
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.middleware.auth_middleware import verify_websocket_token
from src.api.middleware.safe_middleware import get_safe_checker
from src.asr.transcribe import transcribe_audio
from src.core.audio_processing import process_audio_bytes
from src.utils.logging import get_logger

logger = get_logger("api.websocket")
router = APIRouter(tags=["websocket"])

_last_transcription_by_connection: dict[str, dict] = {}
MERGE_WINDOW_SECONDS = 5


def _recent_text(connection_id: str) -> str:
    now = datetime.now(timezone.utc)
    prev = _last_transcription_by_connection.get(connection_id)
    if not prev:
        return ""
    dt = (now - prev["ts"]).total_seconds()
    if dt <= MERGE_WINDOW_SECONDS and prev.get("text"):
        return str(prev["text"])
    return ""


def _remember_text(connection_id: str, text: str) -> None:
    _last_transcription_by_connection[connection_id] = {
        "ts": datetime.now(timezone.utc),
        "text": text,
    }


async def _process_audio_segment(websocket: WebSocket, audio_bytes: bytes, file_id: str, connection_id: str) -> None:
    """Process one audio segment via shared unified pipeline."""
    try:
        result = await process_audio_bytes(
            content=audio_bytes,
            content_type="audio/wav",
            original_filename=f"{file_id}.wav",
            file_id=file_id,
            ingest_stage="ws_audio_received",
            transcription_stage="ws_transcription_saved",
            run_enrichment=True,
            enrichment_prefix=_recent_text(connection_id),
            transcribe_fn=transcribe_audio,
        )
    except Exception as e:
        logger.warning("audio_processing_failed", file_id=file_id, error=str(e))
        await websocket.send_json({"type": "error", "file_id": file_id, "message": str(e)})
        return

    await websocket.send_json(
        {
            "type": "received",
            "file_id": file_id,
            "status": "queued",
        }
    )

    status = result.get("status")
    if status == "filtered":
        await websocket.send_json(
            {
                "type": "filtered",
                "file_id": file_id,
                "reason": result.get("reason", "filtered"),
                "language": result.get("language"),
                "delete_audio": True,
            }
        )
        return

    if status != "transcribed":
        await websocket.send_json(
            {
                "type": "error",
                "file_id": file_id,
                "message": result.get("reason", "processing_failed"),
            }
        )
        return

    payload = result.get("result", {})
    text = payload.get("text", "")
    if text:
        _remember_text(connection_id, text)

    await websocket.send_json(
        {
            "type": "transcription",
            "file_id": file_id,
            "text": text,
            "language": payload.get("language", ""),
            "delete_audio": True,
            "privacy_mode": payload.get("privacy_mode", "audit"),
        }
    )


@router.websocket("/ws/ingest")
async def websocket_ingest(websocket: WebSocket):
    """WebSocket для приёма аудио-сегментов от клиентов."""
    if not verify_websocket_token(websocket):
        logger.warning("websocket_auth_failed", client=websocket.client)
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    connection_id = str(id(websocket))
    logger.info("websocket_ingest_connected", client=websocket.client)
    try:
        while True:
            data = await websocket.receive()
            if "bytes" in data:
                if not data["bytes"]:
                    await websocket.send_json({"type": "error", "message": "Empty audio"})
                    continue
                # ПОЧЕМУ: SAFE size check против DoS через большие payload.
                # check_file_size() принимает Path, поэтому сравниваем с
                # MAX_FILE_SIZE_BYTES напрямую — быстро и без temp file.
                safe = get_safe_checker()
                if safe and len(data["bytes"]) > safe.MAX_FILE_SIZE_BYTES:
                    await websocket.send_json({"type": "error", "message": "File too large"})
                    continue
                file_id = str(uuid.uuid4())
                await _process_audio_segment(websocket, data["bytes"], file_id, connection_id)
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
                        await _process_audio_segment(websocket, audio_bytes, file_id, connection_id)
                    else:
                        await websocket.send_json({"type": "error", "message": "Unknown message type"})
                except (json.JSONDecodeError, KeyError) as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        logger.info("websocket_ingest_disconnected", client=websocket.client)
    except Exception as e:
        logger.error("websocket_ingest_error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        _last_transcription_by_connection.pop(connection_id, None)
