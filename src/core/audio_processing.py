"""Core audio processing helpers shared by REST and WebSocket paths."""
from __future__ import annotations

import asyncio
import tempfile
import threading
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
import numpy as np

from src.asr.acoustic import extract_acoustic_features
from src.asr.transcribe import transcribe_audio
from src.edge.filters import SpeechFilter
from src.memory.semantic_memory import consolidate_to_memory_node, ensure_semantic_memory_tables
from src.security.privacy_pipeline import apply_privacy_mode
from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import ensure_ingest_tables, persist_structured_event, persist_ws_transcription
from src.storage.integrity import append_integrity_event, ensure_integrity_tables
from src.storage.event_log import (
    log_event,
    STAGE_AUDIO_RECEIVED,
    STAGE_ASR_DONE,
    STAGE_ENRICHED,
)
from src.utils.config import settings
from src.utils.logging import get_logger
from src.speaker.storage import ensure_speaker_tables

# ПОЧЕМУ semaphore(1): транскрипция через faster-whisper (ctranslate2) спавнит
# CPU workers. Без лимита: 2 uvicorn workers × N одновременных записей = N*CPU_COUNT
# процессов. Засоряют event loop, жрут 300-400% CPU, API не отвечает.
# semaphore(1) = только 1 транскрипция одновременно. Записи встают в очередь,
# API остаётся отзывчивым. Latency чуть выше, но стабильность гарантирована.
_transcription_semaphore = asyncio.Semaphore(1)
# Для синхронного пути (process_audio_from_artifact_sync) — лимит 1 ASR одновременно.
_transcription_sync_semaphore = threading.Semaphore(1)

logger = get_logger("core.audio_processing")
_speech_filter: SpeechFilter | None = None
_speech_filter_lock = threading.Lock()

ALLOWED_WAV_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/vnd.wave",
    "application/octet-stream",
}

NOISE_PHRASES = frozenset(
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
        "угу",
        "ага",
        "ну",
        "мм",
        "хм",
        "это",
        "ладно",
        "окей",
        "понял",
    }
)

MIN_WORDS = 2
MIN_LANG_PROBABILITY = 0.4
ALLOWED_TRANSCRIPTION_LANGUAGES = {"ru", "kk", "en"}


def _get_speech_filter() -> SpeechFilter:
    global _speech_filter
    if _speech_filter is not None:
        return _speech_filter
    with _speech_filter_lock:
        if _speech_filter is not None:
            return _speech_filter
        _speech_filter = SpeechFilter(
            enabled=settings.FILTER_MUSIC,
            method=settings.FILTER_METHOD,
            sample_rate=settings.AUDIO_SAMPLE_RATE,
        )
    return _speech_filter


def _read_wav_as_numpy(wav_path: Path) -> np.ndarray | None:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            return np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    except Exception as e:
        logger.warning("wav_read_failed", path=str(wav_path), error=str(e))
        return None


def _mark_ingest_status(db_path: Path, ingest_id: str, status: str, error_message: str | None = None) -> None:
    try:
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "UPDATE ingest_queue SET status=?, processed_at=?, error_message=? WHERE id=?",
                (status, datetime.now().isoformat(), error_message, ingest_id),
            )
    except Exception as e:
        logger.warning("ingest_status_update_failed", ingest_id=ingest_id, status=status, error=str(e))


def _check_speech_gate(wav_path: Path) -> tuple[bool, str | None]:
    if not settings.FILTER_MUSIC:
        return True, None
    audio_data = _read_wav_as_numpy(wav_path)
    if audio_data is None:
        return True, None
    sf = _get_speech_filter()
    is_speech_result, metrics = sf.check(audio_data)
    if not is_speech_result:
        logger.info(
            "audio_filtered_not_speech",
            path=str(wav_path),
            speech_ratio=metrics.get("speech_ratio"),
            high_freq_ratio=metrics.get("high_freq_ratio"),
        )
        return False, "not_speech"
    return True, None


def _run_enrichment_sync(
    db_path: Path,
    transcription_id: str,
    result: dict[str, Any],
    enrichment_text: str,
    acoustic_metadata: dict[str, Any] | None = None,
) -> None:
    import time as _time
    from src.enrichment.enricher import enrich_transcription

    _enrich_t0 = _time.monotonic()
    event = enrich_transcription(
        transcription_id=transcription_id,
        text=enrichment_text,
        timestamp=datetime.now(),
        duration_sec=result.get("duration", 0.0) or 0.0,
        language=result.get("language", "unknown") or "unknown",
        acoustic_metadata=acoustic_metadata,
    )
    _enrich_latency_ms = int((_time.monotonic() - _enrich_t0) * 1000)
    persist_structured_event(db_path, event)
    log_event(
        result.get("ingest_id", transcription_id),
        STAGE_ENRICHED,
        latency_ms=_enrich_latency_ms,
        details={
            "model": getattr(event, "enrichment_model", ""),
            "tokens": getattr(event, "enrichment_tokens", 0),
            "transcription_id": transcription_id,
        },
    )
    if settings.MEMORY_ENABLED:
        consolidate_to_memory_node(
            db_path=db_path,
            ingest_id=result.get("ingest_id", ""),
            transcription_id=transcription_id,
            text=result.get("text", ""),
            summary=getattr(event, "summary", "") or "",
            topics=getattr(event, "topics", []) or [],
        )


def is_wav_bytes(content: bytes) -> bool:
    """Minimal WAV magic bytes check (RIFF/WAVE)."""
    if len(content) < 12:
        return False
    return content[:4] == b"RIFF" and content[8:12] == b"WAVE"


def validate_upload_payload(content: bytes, content_type: str | None) -> None:
    """Validate audio content type and signature."""
    if content_type and content_type not in ALLOWED_WAV_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {content_type}")
    if not is_wav_bytes(content):
        raise HTTPException(status_code=400, detail="Invalid WAV file signature")


def validate_safe_file_size(content: bytes, suffix: str, safe_checker: Any, safe_mode: str) -> None:
    """Run SAFE size validation using temp file."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    try:
        size_valid, size_reason = safe_checker.check_file_size(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)

    if not size_valid:
        logger.warning("safe_file_size_check_failed", reason=size_reason, size=len(content))
        if safe_mode == "strict":
            raise HTTPException(status_code=400, detail=f"SAFE validation failed: {size_reason}")


def is_meaningful_transcription(text: str, lang_prob: float = 1.0) -> bool:
    """Check if transcription text likely contains meaningful speech."""
    normalized = (text or "").strip()
    if not normalized:
        return False
    words = normalized.split()
    if len(words) < MIN_WORDS:
        return False
    if normalized.lower() in NOISE_PHRASES:
        return False
    if (lang_prob or 0.0) < MIN_LANG_PROBABILITY:
        return False
    return True


def is_allowed_language(language: str | None) -> bool:
    """Allow only configured core languages for now."""
    if not language:
        return False
    return language.lower() in ALLOWED_TRANSCRIPTION_LANGUAGES


def create_ingest_artifact(
    content: bytes,
    content_type: str | None,
    original_filename: str | None,
    stage: str,
    file_id: str | None = None,
    queue_status: str = "pending",
) -> dict[str, Any]:
    """Persist WAV file and queue row, append integrity event.

    Returns artifact metadata used by handlers.
    """
    validate_upload_payload(content, content_type)

    ingest_id = file_id or str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{ingest_id}.wav"
    dest_path = settings.UPLOADS_PATH / filename
    settings.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(content)

    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_ingest_tables(db_path)
    ensure_integrity_tables(db_path)

    try:
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT OR REPLACE INTO ingest_queue (id, filename, file_path, file_size, status, created_at, processed_at) VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT processed_at FROM ingest_queue WHERE id=?), NULL))",
                (
                    ingest_id,
                    filename,
                    str(dest_path),
                    len(content),
                    queue_status,
                    datetime.now().isoformat(),
                    ingest_id,
                ),
            )
    except Exception as e:
        logger.warning("ingest_queue_upsert_failed", error=str(e), ingest_id=ingest_id)

    if settings.INTEGRITY_CHAIN_ENABLED:
        append_integrity_event(
            db_path=db_path,
            ingest_id=ingest_id,
            stage=stage,
            payload_bytes=content,
            metadata={
                "filename": filename,
                "size": len(content),
                "content_type": content_type or "",
                "original_filename": original_filename or "",
            },
        )

    log_event(ingest_id, STAGE_AUDIO_RECEIVED, details={"filename": filename, "size": len(content)})

    return {
        "ingest_id": ingest_id,
        "filename": filename,
        "dest_path": dest_path,
        "db_path": db_path,
        "size": len(content),
    }


def process_audio_from_artifact_sync(
    ingest_id: str,
    file_path: Path,
    *,
    enrichment_prefix: str | None = None,
    transcription_stage: str = "ws_transcription_saved",
    delete_audio_after: bool | None = None,
    run_enrichment: bool = True,
) -> dict[str, Any]:
    """Обработка уже сохранённого артефакта (WAV + запись в ingest_queue).

    Синхронная версия для вызова из IngestWorker через asyncio.to_thread.
    Выполняет: speech gate → speaker verification → acoustic → ASR → persist → enrichment.
    Не создаёт артефакт — вызывающий код уже вызвал create_ingest_artifact.
    """
    import time as _time

    if delete_audio_after is None:
        delete_audio_after = settings.AUDIO_RETENTION_HOURS == 0
    db_path = settings.STORAGE_PATH / "reflexio.db"
    filename = file_path.name
    file_size = file_path.stat().st_size if file_path.exists() else 0

    ensure_ingest_tables(db_path)
    ensure_integrity_tables(db_path)
    ensure_semantic_memory_tables(db_path)
    ensure_speaker_tables(db_path)

    try:
        allowed_speech, speech_reason = _check_speech_gate(file_path)
        if not allowed_speech:
            _mark_ingest_status(db_path, ingest_id, "filtered", speech_reason)
            if delete_audio_after:
                file_path.unlink(missing_ok=True)
            return {
                "status": "filtered",
                "reason": speech_reason or "not_speech",
                "ingest_id": ingest_id,
                "filename": filename,
            }

        if settings.SPEAKER_VERIFICATION_ENABLED:
            audio_data = _read_wav_as_numpy(file_path)
            if audio_data is not None:
                from src.speaker import verify_speaker

                verification = verify_speaker(
                    audio=audio_data / 32768.0,
                    db_path=db_path,
                    sample_rate=settings.AUDIO_SAMPLE_RATE,
                    amplitude_threshold=settings.SPEAKER_AMPLITUDE_THRESHOLD,
                    similarity_threshold=settings.SPEAKER_SIMILARITY_THRESHOLD,
                )
                logger.info(
                    "speaker_verification",
                    ingest_id=ingest_id,
                    is_user=verification.is_user,
                    confidence=verification.confidence,
                    method=verification.method,
                )
                if not verification.is_user:
                    _mark_ingest_status(db_path, ingest_id, "filtered", "not_user_speaker")
                    if delete_audio_after:
                        file_path.unlink(missing_ok=True)
                    return {
                        "status": "filtered",
                        "reason": "not_user_speaker",
                        "ingest_id": ingest_id,
                        "filename": filename,
                        "speaker_confidence": verification.confidence,
                    }

        acoustic_metadata = extract_acoustic_features(file_path)
        if acoustic_metadata:
            logger.info(
                "acoustic_features",
                ingest_id=ingest_id,
                arousal=acoustic_metadata.get("acoustic_arousal"),
                pitch_var=acoustic_metadata.get("pitch_variance"),
            )

        _asr_t0 = _time.monotonic()
        with _transcription_sync_semaphore:
            result = transcribe_audio(file_path, language=settings.ASR_LANGUAGE)

        text = (result.get("text") or "").strip()
        lang_prob = result.get("language_probability", 1.0) or 1.0
        detected_lang = (result.get("language") or "").lower()

        if not is_allowed_language(detected_lang):
            _mark_ingest_status(db_path, ingest_id, "filtered", f"unsupported_language:{detected_lang or 'unknown'}")
            if delete_audio_after:
                file_path.unlink(missing_ok=True)
            return {
                "status": "filtered",
                "reason": "unsupported_language",
                "language": detected_lang or "unknown",
                "ingest_id": ingest_id,
                "filename": filename,
            }

        if not is_meaningful_transcription(text, lang_prob):
            _mark_ingest_status(db_path, ingest_id, "filtered", "noise")
            if delete_audio_after:
                file_path.unlink(missing_ok=True)
            return {
                "status": "filtered",
                "reason": "noise",
                "ingest_id": ingest_id,
                "filename": filename,
            }

        privacy = apply_privacy_mode(text, mode=settings.PRIVACY_MODE)
        if not privacy.allowed:
            _mark_ingest_status(db_path, ingest_id, "filtered", "pii_blocked")
            if delete_audio_after:
                file_path.unlink(missing_ok=True)
            return {
                "status": "filtered",
                "reason": "pii_blocked",
                "ingest_id": ingest_id,
                "filename": filename,
            }

        result["text"] = privacy.text
        result["privacy_mode"] = privacy.mode
        result["pii_count"] = privacy.pii_count
        result["ingest_id"] = ingest_id

        transcription_id = persist_ws_transcription(
            db_path=db_path,
            file_id=ingest_id,
            filename=filename,
            file_path=str(file_path),
            file_size=file_size,
            result=result,
        )

        if settings.INTEGRITY_CHAIN_ENABLED:
            append_integrity_event(
                db_path=db_path,
                ingest_id=ingest_id,
                stage=transcription_stage,
                payload_text=result.get("text", ""),
                metadata={"language": result.get("language", ""), "privacy_mode": privacy.mode},
            )

        _mark_ingest_status(db_path, ingest_id, "processed")
        _asr_latency_ms = int((_time.monotonic() - _asr_t0) * 1000)
        log_event(
            ingest_id,
            STAGE_ASR_DONE,
            latency_ms=_asr_latency_ms,
            details={"words": len(text.split()), "lang": detected_lang, "transcription_id": transcription_id},
        )
        if delete_audio_after:
            file_path.unlink(missing_ok=True)

        if run_enrichment and transcription_id:
            text_for_enrichment = f"{(enrichment_prefix or '').strip()} {result.get('text', '').strip()}".strip()
            _run_enrichment_sync(
                db_path=db_path,
                transcription_id=transcription_id,
                result=result,
                enrichment_text=text_for_enrichment,
                acoustic_metadata=acoustic_metadata,
            )

        return {
            "status": "transcribed",
            "ingest_id": ingest_id,
            "filename": filename,
            "transcription_id": transcription_id,
            "result": result,
        }
    except Exception as e:
        _mark_ingest_status(db_path, ingest_id, "error", str(e))
        if delete_audio_after:
            file_path.unlink(missing_ok=True)
        logger.warning("process_audio_from_artifact_failed", ingest_id=ingest_id, error=str(e))
        raise


async def process_audio_bytes(
    content: bytes,
    content_type: str | None,
    original_filename: str | None,
    *,
    file_id: str | None = None,
    ingest_stage: str = "audio_received",
    transcription_stage: str = "transcription_saved",
    delete_audio_after: bool | None = None,  # None = читать из settings.AUDIO_RETENTION_HOURS
    run_enrichment: bool = True,
    enrichment_text: str | None = None,
    enrichment_prefix: str | None = None,
    transcribe_fn: Any | None = None,
    fail_open: bool = False,
    transcribe_now: bool = True,
) -> dict[str, Any]:
    """Unified production processing for REST and WebSocket audio ingest."""
    if delete_audio_after is None:
        delete_audio_after = settings.AUDIO_RETENTION_HOURS == 0
    artifact = create_ingest_artifact(
        content=content,
        content_type=content_type,
        original_filename=original_filename,
        stage=ingest_stage,
        file_id=file_id,
        queue_status="pending",
    )
    db_path = artifact["db_path"]
    dest_path = artifact["dest_path"]
    ingest_id = artifact["ingest_id"]
    filename = artifact["filename"]

    ensure_ingest_tables(db_path)
    ensure_integrity_tables(db_path)
    ensure_semantic_memory_tables(db_path)
    ensure_speaker_tables(db_path)

    if not transcribe_now:
        return {
            "status": "received",
            "ingest_id": ingest_id,
            "filename": filename,
        }

    try:
        allowed_speech, speech_reason = _check_speech_gate(dest_path)
        if not allowed_speech:
            _mark_ingest_status(db_path, ingest_id, "filtered", speech_reason)
            if delete_audio_after:
                dest_path.unlink(missing_ok=True)
            return {
                "status": "filtered",
                "reason": speech_reason or "not_speech",
                "ingest_id": ingest_id,
                "filename": filename,
            }

        # P4: Speaker verification (ПЕРЕД Whisper — экономия 3-5с на фоновых голосах)
        # ПОЧЕМУ здесь: аудиофайл ещё существует, Whisper ещё не запущен.
        # Если говорит не пользователь (ТВ, радио, коллеги) — пропускаем дорогой ASR.
        if settings.SPEAKER_VERIFICATION_ENABLED:
            audio_data = _read_wav_as_numpy(dest_path)
            if audio_data is not None:
                from src.speaker import verify_speaker

                verification = verify_speaker(
                    audio=audio_data / 32768.0,  # int16 → float32 [-1, 1]
                    db_path=db_path,
                    sample_rate=settings.AUDIO_SAMPLE_RATE,
                    amplitude_threshold=settings.SPEAKER_AMPLITUDE_THRESHOLD,
                    similarity_threshold=settings.SPEAKER_SIMILARITY_THRESHOLD,
                )
                logger.info(
                    "speaker_verification",
                    ingest_id=ingest_id,
                    is_user=verification.is_user,
                    confidence=verification.confidence,
                    method=verification.method,
                )
                if not verification.is_user:
                    _mark_ingest_status(db_path, ingest_id, "filtered", "not_user_speaker")
                    if delete_audio_after:
                        dest_path.unlink(missing_ok=True)
                    return {
                        "status": "filtered",
                        "reason": "not_user_speaker",
                        "ingest_id": ingest_id,
                        "filename": filename,
                        "speaker_confidence": verification.confidence,
                    }

        # Stage 2.5: Acoustic features — ПЕРЕД Whisper, пока WAV жив.
        # ПОЧЕМУ здесь: после ASR аудио удаляется (zero-retention).
        # Акустика даёт LLM второй канал данных для эмоций.
        acoustic_metadata = extract_acoustic_features(dest_path)
        if acoustic_metadata:
            logger.info(
                "acoustic_features",
                ingest_id=ingest_id,
                arousal=acoustic_metadata.get("acoustic_arousal"),
                pitch_var=acoustic_metadata.get("pitch_variance"),
            )

        import time as _time
        transcriber = transcribe_fn or transcribe_audio
        _asr_t0 = _time.monotonic()
        # ПОЧЕМУ semaphore + run_in_executor:
        # transcribe_audio() — синхронная блокирующая CPU операция.
        # Прямой вызов из async → блокирует asyncio event loop → uvicorn не отвечает.
        # run_in_executor → выполняется в отдельном потоке, event loop свободен.
        # semaphore(1) → только 1 транскрипция одновременно, CPU не перегружается.
        loop = asyncio.get_event_loop()
        async with _transcription_semaphore:
            result = await loop.run_in_executor(
                None,
                lambda: transcriber(dest_path, language=settings.ASR_LANGUAGE),
            )
        _asr_latency_ms = int((_time.monotonic() - _asr_t0) * 1000)
        text = (result.get("text") or "").strip()
        lang_prob = result.get("language_probability", 1.0) or 1.0
        detected_lang = (result.get("language") or "").lower()

        if not is_allowed_language(detected_lang):
            _mark_ingest_status(db_path, ingest_id, "filtered", f"unsupported_language:{detected_lang or 'unknown'}")
            if delete_audio_after:
                dest_path.unlink(missing_ok=True)
            return {
                "status": "filtered",
                "reason": "unsupported_language",
                "language": detected_lang or "unknown",
                "ingest_id": ingest_id,
                "filename": filename,
            }

        if not is_meaningful_transcription(text, lang_prob):
            _mark_ingest_status(db_path, ingest_id, "filtered", "noise")
            if delete_audio_after:
                dest_path.unlink(missing_ok=True)
            return {
                "status": "filtered",
                "reason": "noise",
                "ingest_id": ingest_id,
                "filename": filename,
            }

        privacy = apply_privacy_mode(text, mode=settings.PRIVACY_MODE)
        if not privacy.allowed:
            _mark_ingest_status(db_path, ingest_id, "filtered", "pii_blocked")
            if delete_audio_after:
                dest_path.unlink(missing_ok=True)
            return {
                "status": "filtered",
                "reason": "pii_blocked",
                "ingest_id": ingest_id,
                "filename": filename,
            }

        result["text"] = privacy.text
        result["privacy_mode"] = privacy.mode
        result["pii_count"] = privacy.pii_count
        result["ingest_id"] = ingest_id

        transcription_id = persist_ws_transcription(
            db_path=db_path,
            file_id=ingest_id,
            filename=filename,
            file_path=str(dest_path),
            file_size=len(content),
            result=result,
        )

        if settings.INTEGRITY_CHAIN_ENABLED:
            append_integrity_event(
                db_path=db_path,
                ingest_id=ingest_id,
                stage=transcription_stage,
                payload_text=result.get("text", ""),
                metadata={"language": result.get("language", ""), "privacy_mode": privacy.mode},
            )

        _mark_ingest_status(db_path, ingest_id, "processed")
        log_event(
            ingest_id,
            STAGE_ASR_DONE,
            latency_ms=_asr_latency_ms,
            details={"words": len(text.split()), "lang": detected_lang, "transcription_id": transcription_id},
        )
        if delete_audio_after:
            dest_path.unlink(missing_ok=True)

        if run_enrichment and transcription_id:
            text_for_enrichment = enrichment_text or f"{(enrichment_prefix or '').strip()} {result.get('text', '').strip()}".strip()
            from src.enrichment.worker import get_enrichment_worker, EnrichmentTask
            worker = get_enrichment_worker()
            await worker.submit(EnrichmentTask(
                db_path=db_path,
                transcription_id=transcription_id,
                result=result,
                enrichment_text=text_for_enrichment,
                acoustic_metadata=acoustic_metadata,
            ))

        return {
            "status": "transcribed",
            "ingest_id": ingest_id,
            "filename": filename,
            "transcription_id": transcription_id,
            "result": result,
        }
    except Exception as e:
        _mark_ingest_status(db_path, ingest_id, "error", "processing_failed")
        if delete_audio_after:
            dest_path.unlink(missing_ok=True)
        if fail_open:
            logger.warning("process_audio_fail_open", ingest_id=ingest_id, error=str(e))
            return {
                "status": "received",
                "ingest_id": ingest_id,
                "filename": filename,
                "reason": "processing_deferred",
            }
        raise










