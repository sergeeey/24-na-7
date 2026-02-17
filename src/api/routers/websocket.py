"""Роутер для WebSocket endpoints."""
import json
import uuid
import base64
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.utils.config import settings
from src.utils.logging import get_logger
from src.asr.transcribe import transcribe_audio
from src.storage.ingest_persist import persist_ws_transcription

logger = get_logger("api.websocket")
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/ingest")
async def websocket_ingest(websocket: WebSocket):
    """
    WebSocket для приёма аудио-сегментов от клиентов (например Android).
    
    Клиент отправляет: бинарный WAV или JSON { "type": "audio", "data": "<base64>" }.
    Сервер отвечает: { "type": "received", "file_id": "...", "status": "queued" },
    затем при готовности { "type": "transcription", "file_id": "...", "text": "..." } или { "type": "error", ... }.
    
    **Пример использования:**
    ```python
    import websockets
    import asyncio
    
    async def send_audio():
        async with websockets.connect("ws://localhost:8000/ws/ingest") as ws:
            # Отправка бинарного WAV
            with open("audio.wav", "rb") as f:
                await ws.send(f.read())
            
            # Получение ответов
            response = await ws.recv()
            print(json.loads(response))
    ```
    """
    await websocket.accept()
    logger.info("websocket_ingest_connected", client=websocket.client)
    try:
        while True:
            data = await websocket.receive()
            if "bytes" in data:
                if not data["bytes"]:
                    await websocket.send_json({"type": "error", "message": "Empty audio"})
                    continue
                # Бинарный фрейм — сохраняем как WAV
                file_id = str(uuid.uuid4())
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}_{file_id}.wav"
                dest_path = settings.UPLOADS_PATH / filename
                settings.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(data["bytes"])
                await websocket.send_json({
                    "type": "received",
                    "file_id": file_id,
                    "status": "queued",
                    "filename": filename,
                })
                # Транскрибируем и сохраняем в БД для дайджеста
                try:
                    result = transcribe_audio(dest_path)
                    db_path = settings.STORAGE_PATH / "reflexio.db"
                    persist_ws_transcription(
                        db_path=db_path,
                        file_id=file_id,
                        filename=filename,
                        file_path=str(dest_path),
                        file_size=len(data["bytes"]),
                        result=result,
                    )
                    await websocket.send_json({
                        "type": "transcription",
                        "file_id": file_id,
                        "text": result.get("text", ""),
                        "language": result.get("language", ""),
                    })
                except Exception as e:
                    logger.warning("websocket_transcribe_failed", file_id=file_id, error=str(e))
                    await websocket.send_json({
                        "type": "error",
                        "file_id": file_id,
                        "message": str(e),
                    })
            elif "text" in data and data["text"]:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "audio" and msg.get("data"):
                        file_id = str(uuid.uuid4())
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"{timestamp}_{file_id}.wav"
                        dest_path = settings.UPLOADS_PATH / filename
                        settings.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
                        dest_path.write_bytes(base64.b64decode(msg["data"]))
                        await websocket.send_json({
                            "type": "received",
                            "file_id": file_id,
                            "status": "queued",
                            "filename": filename,
                        })
                        try:
                            result = transcribe_audio(dest_path)
                            db_path = settings.STORAGE_PATH / "reflexio.db"
                            persist_ws_transcription(
                                db_path=db_path,
                                file_id=file_id,
                                filename=filename,
                                file_path=str(dest_path),
                                file_size=len(base64.b64decode(msg["data"])),
                                result=result,
                            )
                            await websocket.send_json({
                                "type": "transcription",
                                "file_id": file_id,
                                "text": result.get("text", ""),
                                "language": result.get("language", ""),
                            })
                        except Exception as e:
                            logger.warning("websocket_transcribe_failed", file_id=file_id, error=str(e))
                            await websocket.send_json({"type": "error", "file_id": file_id, "message": str(e)})
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
