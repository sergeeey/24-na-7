"""Роутер для WebSocket endpoints."""
import base64
import json
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.middleware.auth_middleware import verify_websocket_token
from src.asr.transcribe import transcribe_audio
from src.edge.filters import SpeechFilter
from src.memory.semantic_memory import consolidate_to_memory_node, ensure_semantic_memory_tables
from src.security.privacy_pipeline import apply_privacy_mode
from src.storage.ingest_persist import (
    ensure_ingest_tables,
    persist_structured_event,
    persist_ws_transcription,
)
from src.storage.integrity import append_integrity_event, ensure_integrity_tables
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api.websocket")
router = APIRouter(tags=["websocket"])

_speech_filter: Optional[SpeechFilter] = None


def _get_speech_filter() -> SpeechFilter:
    global _speech_filter
    if _speech_filter is None:
        _speech_filter = SpeechFilter(
            enabled=settings.FILTER_MUSIC,
            method=settings.FILTER_METHOD,
            sample_rate=settings.AUDIO_SAMPLE_RATE,
        )
    return _speech_filter


def _read_wav_as_numpy(wav_path: Path) -> Optional[np.ndarray]:
    """Read WAV file as numpy array for speech filter."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            return audio
    except Exception as e:
        logger.warning("wav_read_failed", path=str(wav_path), error=str(e))
        return None


_NOISE_PHRASES = frozenset(
    {
        "you",
        "the",
        "a",
        "an",
        "i",
        "he",
        "she",
        "it",
        "we",
        "they",
        "yes",
        "no",
        "oh",
        "ah",
        "um",
        "uh",
        "hmm",
        "huh",
        "that's it",
        "thank you",
        "thanks",
        "okay",
        "ok",
    }
)
_MIN_WORDS = 3
_MIN_LANG_PROBABILITY = 0.4


def _is_meaningful_transcription(text: str, lang_prob: float = 1.0) -> bool:
    """Check if transcription contains meaningful speech (not noise)."""
    text = text.strip()
    if not text:
        return False
    words = text.split()
    if len(words) < _MIN_WORDS:
        return False
    if text.lower() in _NOISE_PHRASES:
        return False
    if lang_prob < _MIN_LANG_PROBABILITY:
        return False
    return True


def _enrich_and_persist(db_path, transcription_id: str, result: dict) -> None:
    """Enrichment в отдельном try/except — не ломает pipeline при ошибке."""
    try:
        from src.enrichment.enricher import enrich_transcription

        event = enrich_transcription(
            transcription_id=transcription_id,
            text=result.get("text", ""),
            timestamp=datetime.now(),
            duration_sec=result.get("duration", 0.0) or 0.0,
            language=result.get("language", "unknown") or "unknown",
        )
        persist_structured_event(db_path, event)
        if settings.MEMORY_ENABLED:
            consolidate_to_memory_node(
                db_path=db_path,
                ingest_id=result.get("ingest_id", ""),
                transcription_id=transcription_id,
                text=result.get("text", ""),
                summary=getattr(event, "summary", "") or "",
                topics=getattr(event, "topics", []) or [],
            )
    except Exception as e:
        logger.debug("enrichment_skipped", transcription_id=transcription_id, error=str(e))


async def _process_audio_segment(websocket: WebSocket, audio_bytes: bytes, file_id: str) -> None:
    """Process one audio segment: filter -> transcribe -> persist -> cleanup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file_id}.wav"
    dest_path = settings.UPLOADS_PATH / filename
    settings.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(audio_bytes)

    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_ingest_tables(db_path)
    ensure_integrity_tables(db_path)
    ensure_semantic_memory_tables(db_path)

    if settings.INTEGRITY_CHAIN_ENABLED:
        append_integrity_event(
            db_path=db_path,
            ingest_id=file_id,
            stage="ws_audio_received",
            payload_bytes=audio_bytes,
            metadata={"filename": filename, "size": len(audio_bytes)},
        )

    await websocket.send_json(
        {
            "type": "received",
            "file_id": file_id,
            "status": "queued",
            "filename": filename,
        }
    )

    try:
        if settings.FILTER_MUSIC:
            audio_data = _read_wav_as_numpy(dest_path)
            if audio_data is not None:
                sf = _get_speech_filter()
                is_speech_result, metrics = sf.check(audio_data)
                if not is_speech_result:
                    logger.info(
                        "audio_filtered_not_speech",
                        file_id=file_id,
                        speech_ratio=metrics.get("speech_ratio"),
                        high_freq_ratio=metrics.get("high_freq_ratio"),
                    )
                    dest_path.unlink(missing_ok=True)
                    await websocket.send_json(
                        {
                            "type": "filtered",
                            "file_id": file_id,
                            "reason": "not_speech",
                            "delete_audio": True,
                        }
                    )
                    return

        result = transcribe_audio(dest_path, language=settings.ASR_LANGUAGE)

        text = (result.get("text") or "").strip()
        lang_prob = result.get("language_probability", 1.0) or 1.0
        if not _is_meaningful_transcription(text, lang_prob):
            logger.info("transcription_filtered_noise", file_id=file_id, text=text[:50], lang_prob=lang_prob)
            dest_path.unlink(missing_ok=True)
            await websocket.send_json(
                {
                    "type": "filtered",
                    "file_id": file_id,
                    "reason": "noise",
                    "delete_audio": True,
                }
            )
            return

        privacy = apply_privacy_mode(text, mode=settings.PRIVACY_MODE)
        if not privacy.allowed:
            dest_path.unlink(missing_ok=True)
            await websocket.send_json(
                {
                    "type": "filtered",
                    "file_id": file_id,
                    "reason": "pii_blocked",
                    "delete_audio": True,
                }
            )
            return

        result["text"] = privacy.text
        result["privacy_mode"] = privacy.mode
        result["pii_count"] = privacy.pii_count
        result["ingest_id"] = file_id

        transcription_id = persist_ws_transcription(
            db_path=db_path,
            file_id=file_id,
            filename=filename,
            file_path=str(dest_path),
            file_size=len(audio_bytes),
            result=result,
        )

        if settings.INTEGRITY_CHAIN_ENABLED:
            append_integrity_event(
                db_path=db_path,
                ingest_id=file_id,
                stage="ws_transcription_saved",
                payload_text=result.get("text", ""),
                metadata={"language": result.get("language", ""), "privacy_mode": privacy.mode},
            )

        dest_path.unlink(missing_ok=True)
        logger.debug("wav_deleted_after_transcription", file_id=file_id, filename=filename)

        await websocket.send_json(
            {
                "type": "transcription",
                "file_id": file_id,
                "text": result.get("text", ""),
                "language": result.get("language", ""),
                "delete_audio": True,
                "privacy_mode": privacy.mode,
            }
        )

        if transcription_id:
            _enrich_and_persist(db_path, transcription_id, result)

    except Exception as e:
        logger.warning("audio_processing_failed", file_id=file_id, error=str(e))
        dest_path.unlink(missing_ok=True)
        await websocket.send_json({"type": "error", "file_id": file_id, "message": str(e)})


@router.websocket("/ws/ingest")
async def websocket_ingest(websocket: WebSocket):
    """WebSocket для приёма аудио-сегментов от клиентов."""
    if not verify_websocket_token(websocket):
        logger.warning("websocket_auth_failed", client=websocket.client)
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    logger.info("websocket_ingest_connected", client=websocket.client)
    try:
        while True:
            data = await websocket.receive()
            if "bytes" in data:
                if not data["bytes"]:
                    await websocket.send_json({"type": "error", "message": "Empty audio"})
                    continue
                file_id = str(uuid.uuid4())
                await _process_audio_segment(websocket, data["bytes"], file_id)
            elif "text" in data and data["text"]:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "audio" and msg.get("data"):
                        file_id = str(uuid.uuid4())
                        await _process_audio_segment(websocket, base64.b64decode(msg["data"]), file_id)
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
