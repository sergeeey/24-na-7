"""Роутер для WebSocket endpoints."""
import json
import uuid
import wave
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.utils.config import settings
from src.utils.logging import get_logger
from src.asr.transcribe import transcribe_audio
from src.storage.ingest_persist import persist_ws_transcription, persist_structured_event
from src.api.middleware.auth_middleware import verify_websocket_token
from src.edge.filters import SpeechFilter

logger = get_logger("api.websocket")
router = APIRouter(tags=["websocket"])

# --- P0: Speech filter (music/noise rejection) ---
# ПОЧЕМУ lazy init: SpeechFilter может подгружать librosa, не нужен при старте.
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


# --- P1: Noise transcription filter ---
# ПОЧЕМУ дублирование с DigestGenerator: WebSocket handler НЕ должен зависеть
# от digest модуля — это разные слои. Фильтр здесь отсекает мусор ДО записи в БД,
# а DigestGenerator фильтрует то что уже в БД (вторая линия обороны).
_NOISE_PHRASES = frozenset({
    "you", "the", "a", "an", "i", "he", "she", "it", "we", "they",
    "yes", "no", "oh", "ah", "um", "uh", "hmm", "huh",
    "that's it", "thank you", "thanks", "okay", "ok",
})
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
    """Enrichment в отдельном try/except — не ломает pipeline при ошибке.

    ПОЧЕМУ lazy import: enricher тянет LLM-клиент, не нужен при старте.
    """
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
    except Exception as e:
        logger.debug("enrichment_skipped", transcription_id=transcription_id, error=str(e))


async def _process_audio_segment(
    websocket: WebSocket,
    audio_bytes: bytes,
    file_id: str,
) -> None:
    """Process one audio segment: filter → transcribe → persist → cleanup.

    ПОЧЕМУ отдельная функция: binary и base64 пути используют одинаковую логику.
    Без этого — 60 строк дупликации и 2 места для багов.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file_id}.wav"
    dest_path = settings.UPLOADS_PATH / filename
    settings.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(audio_bytes)

    await websocket.send_json({
        "type": "received",
        "file_id": file_id,
        "status": "queued",
        "filename": filename,
    })

    try:
        # P0: Speech filter — отсекаем музыку/шум ДО дорогой транскрипции
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
                    await websocket.send_json({
                        "type": "filtered",
                        "file_id": file_id,
                        "reason": "not_speech",
                        "delete_audio": True,
                    })
                    return

        # Транскрибируем
        result = transcribe_audio(dest_path)

        # P1: Filter noise — отсекаем "you you you" ДО записи в БД
        text = (result.get("text") or "").strip()
        lang_prob = result.get("language_probability", 1.0) or 1.0
        if not _is_meaningful_transcription(text, lang_prob):
            logger.info(
                "transcription_filtered_noise",
                file_id=file_id,
                text=text[:50],
                lang_prob=lang_prob,
            )
            dest_path.unlink(missing_ok=True)
            await websocket.send_json({
                "type": "filtered",
                "file_id": file_id,
                "reason": "noise",
                "delete_audio": True,
            })
            return

        # Persist в БД
        db_path = settings.STORAGE_PATH / "reflexio.db"
        transcription_id = persist_ws_transcription(
            db_path=db_path,
            file_id=file_id,
            filename=filename,
            file_path=str(dest_path),
            file_size=len(audio_bytes),
            result=result,
        )

        # P2: Delete WAV — текст уже в БД, файл больше не нужен
        dest_path.unlink(missing_ok=True)
        logger.debug("wav_deleted_after_transcription", file_id=file_id, filename=filename)

        # Отправляем результат клиенту (P3: delete_audio сигнал)
        await websocket.send_json({
            "type": "transcription",
            "file_id": file_id,
            "text": result.get("text", ""),
            "language": result.get("language", ""),
            "delete_audio": True,
        })

        # ПОЧЕМУ после send_json: клиент получает ответ сразу,
        # enrichment (LLM ~1-2с) не блокирует UX
        if transcription_id:
            _enrich_and_persist(db_path, transcription_id, result)

    except Exception as e:
        logger.warning("audio_processing_failed", file_id=file_id, error=str(e))
        # P2: Cleanup WAV even on error
        dest_path.unlink(missing_ok=True)
        await websocket.send_json({
            "type": "error",
            "file_id": file_id,
            "message": str(e),
        })


@router.websocket("/ws/ingest")
async def websocket_ingest(websocket: WebSocket):
    """
    WebSocket для приёма аудио-сегментов от клиентов (например Android).

    Клиент отправляет: бинарный WAV или JSON { "type": "audio", "data": "<base64>" }.
    Сервер отвечает:
    - { "type": "received", "file_id": "...", "status": "queued" }
    - { "type": "transcription", "file_id": "...", "text": "...", "delete_audio": true }
    - { "type": "filtered", "file_id": "...", "reason": "...", "delete_audio": true }
    - { "type": "error", ... }
    """
    # ПОЧЕМУ проверяем ДО accept(): если ключ неверный, даже не открываем
    # соединение — клиент получит HTTP 403 вместо upgrade.
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
                        await _process_audio_segment(
                            websocket, base64.b64decode(msg["data"]), file_id
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
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
