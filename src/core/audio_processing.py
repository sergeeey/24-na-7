"""Core audio processing helpers shared by REST and WebSocket paths."""

from __future__ import annotations

import asyncio
import json
import hashlib
import re
import tempfile
import threading
import uuid
import wave
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
import numpy as np

from src.asr.acoustic import extract_acoustic_features
from src.asr.transcribe import transcribe_audio
from src.edge.filters import SpeechFilter
from src.memory.episodes import (
    attach_transcription_to_episode,
    get_episode_context,
    refresh_episode_from_event,
)
from src.memory.truth import apply_episode_truth_state, evaluate_episode_truth
from src.memory.semantic_memory import consolidate_to_memory_node, ensure_semantic_memory_tables
from src.security.privacy_pipeline import apply_privacy_mode
from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import (
    ensure_ingest_tables,
    get_existing_ingest,
    get_transcription_by_ingest_id,
    persist_structured_event,
    persist_ws_transcription,
)
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
TRANSCRIPT_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{2,}")

# ПОЧЕМУ 2 слова: одиночные слова ("угу", "ладно") — это шум, а не осмысленная речь.
# 2 слова = минимальная единица смысла ("идём домой", "позвони маме").
MIN_WORDS = 2
# ПОЧЕМУ 0.4: Whisper confidence < 0.4 = фоновый шум или чужая речь.
# Тестировано: 0.3 пропускает мусор, 0.5 режет казахский (kk) с акцентом.
MIN_LANG_PROBABILITY = 0.4
# ПОЧЕМУ именно эти: основные языки пользователя (Алматы, КЗ).
# Всё остальное (zh, ar, ...) = Whisper галлюцинирует на фоновом шуме.
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


def _mark_ingest_status(
    db_path: Path,
    ingest_id: str,
    status: str,
    error_message: str | None = None,
    *,
    transport_status: str | None = None,
    processing_status: str | None = None,
    error_code: str | None = None,
    quarantine_reason: str | None = None,
    quality_score: float | None = None,
    needs_recheck: bool | None = None,
) -> None:
    try:
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                UPDATE ingest_queue
                SET status=?,
                    processed_at=?,
                    error_message=?,
                    transport_status=COALESCE(?, transport_status),
                    processing_status=COALESCE(?, processing_status),
                    error_code=COALESCE(?, error_code),
                    quarantine_reason=COALESCE(?, quarantine_reason),
                    quality_score=COALESCE(?, quality_score),
                    needs_recheck=COALESCE(?, needs_recheck)
                WHERE id=?
                """,
                (
                    status,
                    datetime.now().isoformat(),
                    error_message,
                    transport_status,
                    processing_status,
                    error_code,
                    quarantine_reason,
                    quality_score,
                    None if needs_recheck is None else int(needs_recheck),
                    ingest_id,
                ),
            )
    except Exception as e:
        logger.warning(
            "ingest_status_update_failed", ingest_id=ingest_id, status=status, error=str(e)
        )


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


def _precheck_audio_artifact(wav_path: Path) -> tuple[bool, str | None]:
    """Cheap guardrails before expensive ASR."""
    try:
        if not wav_path.exists() or wav_path.stat().st_size <= 44:
            return False, "empty_audio"
        with wave.open(str(wav_path), "rb") as wf:
            frame_count = wf.getnframes()
            sample_rate = wf.getframerate() or settings.AUDIO_SAMPLE_RATE
            duration = frame_count / float(sample_rate or 1)
        if duration < 0.2:
            return False, "too_short"
    except Exception:
        return False, "invalid_wav"

    audio_data = _read_wav_as_numpy(wav_path)
    if audio_data is None or audio_data.size == 0:
        return False, "invalid_wav"
    clipped_ratio = float(np.mean(np.abs(audio_data) >= 32760))
    if clipped_ratio > 0.25:
        return False, "clipping"
    return True, None


def _assess_transcription_quality(result: dict[str, Any]) -> tuple[float, bool, bool]:
    """Return quality_score, needs_recheck, garbage_flag."""
    text = (result.get("text") or "").strip()
    duration = float(result.get("duration") or 0.0)
    language = (result.get("language") or "").lower()
    lang_prob = float(result.get("language_probability") or 0.0)
    words = [w for w in text.split() if w.strip()]
    unique_ratio = (len(set(w.lower() for w in words)) / len(words)) if words else 0.0
    chars_per_second = (len(text) / duration) if duration > 0 else 0.0

    score = 1.0
    if not text:
        score -= 0.8
    if duration >= 4.0 and len(words) < 2:
        score -= 0.45
    if chars_per_second > 25:
        score -= 0.2
    if unique_ratio < 0.45 and len(words) >= 4:
        score -= 0.2
    if not is_allowed_language(language):
        score -= 0.2
    if lang_prob < MIN_LANG_PROBABILITY:
        score -= 0.15

    score = max(0.0, min(1.0, score))
    garbage_flag = (len(words) >= 4 and unique_ratio < 0.3) or chars_per_second > 35
    needs_recheck = score < 0.55 or garbage_flag
    return score, needs_recheck, garbage_flag


def _normalize_transcript_signature(text: str) -> str:
    tokens = [
        token
        for token in TRANSCRIPT_TOKEN_RE.findall((text or "").lower())
        if token not in NOISE_PHRASES and len(token) > 1
    ]
    if len(tokens) < 2:
        return ""
    return " ".join(tokens[:12])


def _assess_contextual_transcription_risk(
    db_path: Path,
    transcription_id: str,
    episode_id: str | None,
    result: dict[str, Any],
) -> tuple[bool, str | None, float]:
    text = (result.get("transcript_clean") or result.get("text") or "").strip()
    words = [token.lower() for token in TRANSCRIPT_TOKEN_RE.findall(text)]
    signature = _normalize_transcript_signature(text)
    if not words or not signature:
        return False, None, 0.0

    counts = Counter(words)
    dominant_share = max(counts.values()) / len(words)
    bigrams = list(zip(words, words[1:]))
    repeated_bigram_count = max(Counter(bigrams).values(), default=0)
    if len(words) >= 6 and (dominant_share >= 0.45 or repeated_bigram_count >= 2):
        return True, "repeated_phrase_pattern", 0.45

    db = get_reflexio_db(db_path)
    recent_rows = db.fetchall(
        """
        SELECT id, transcript_clean, text
        FROM transcriptions
        WHERE id != ?
          AND created_at >= datetime('now', '-20 minutes')
        ORDER BY created_at DESC
        LIMIT 8
        """,
        (transcription_id,),
    )
    duplicate_neighbors = 0
    for row in recent_rows:
        recent_signature = _normalize_transcript_signature(
            row["transcript_clean"] or row["text"] or ""
        )
        if recent_signature and recent_signature == signature:
            duplicate_neighbors += 1
    if duplicate_neighbors >= 2:
        return True, "duplicate_neighbor_pattern", 0.4

    episode_context = get_episode_context(db_path, episode_id)
    if episode_context:
        topics = json.loads(episode_context.get("topics_json") or "[]")
        topic_tokens = {
            token.lower()
            for topic in topics
            for token in TRANSCRIPT_TOKEN_RE.findall(str(topic))
        }
        if (
            len(words) >= 6
            and topic_tokens
            and not any(token in topic_tokens for token in words)
            and dominant_share >= 0.4
        ):
            return True, "episode_context_mismatch", 0.3

    return False, None, 0.0


def _mark_transcription_for_review(
    db_path: Path,
    transcription_id: str,
    episode_id: str | None,
    quality_score: float,
) -> None:
    db = get_reflexio_db(db_path)
    with db.transaction():
        db.execute(
            """
            UPDATE transcriptions
            SET quality_score = ?,
                needs_recheck = 1,
                garbage_flag = 1
            WHERE id = ?
            """,
            (quality_score, transcription_id),
        )
        if episode_id:
            db.execute(
                "UPDATE episodes SET needs_review = 1 WHERE id = ?",
                (episode_id,),
            )


def _apply_episode_truth_gate(
    db_path: Path,
    ingest_id: str,
    transcription_id: str | None,
    episode_id: str | None,
    *,
    source: str = "gate",
) -> dict[str, Any] | None:
    if not transcription_id or not episode_id:
        return None
    truth = evaluate_episode_truth(db_path, episode_id)
    if not truth:
        return None
    apply_episode_truth_state(db_path, episode_id, truth, source=source)
    quality_state = truth["quality_state"]
    if quality_state == "quarantined":
        _mark_ingest_status(
            db_path,
            ingest_id,
            "quarantined",
            "episode_quality_quarantined",
            transport_status="server_acked",
            processing_status="quarantined",
            error_code="episode_quality_quarantined",
            quarantine_reason="episode_quality_quarantined",
            quality_score=truth["quality_score"],
            needs_recheck=True,
        )
    elif quality_state == "garbage":
        _mark_ingest_status(
            db_path,
            ingest_id,
            "filtered",
            "episode_quality_garbage",
            transport_status="server_acked",
            processing_status="filtered",
            error_code="episode_quality_garbage",
            quality_score=truth["quality_score"],
            needs_recheck=True,
        )
    else:
        _mark_ingest_status(
            db_path,
            ingest_id,
            "transcribed",
            transport_status="server_acked",
            processing_status="transcribed",
            quality_score=truth["quality_score"],
            needs_recheck=truth["needs_recheck"],
        )
    return truth


def _episode_duration_seconds(episode_context: dict[str, Any] | None, fallback: float) -> float:
    if not episode_context:
        return fallback
    started_at = episode_context.get("started_at")
    ended_at = episode_context.get("ended_at")
    try:
        if started_at and ended_at:
            return max(
                0.0,
                (
                    datetime.fromisoformat(str(ended_at).replace("Z", "+00:00"))
                    - datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                ).total_seconds(),
            )
    except ValueError:
        pass
    return fallback


def _run_enrichment_sync(
    db_path: Path,
    transcription_id: str,
    result: dict[str, Any],
    enrichment_text: str,
    acoustic_metadata: dict[str, Any] | None = None,
) -> None:
    import time as _time
    from src.enrichment.enricher import enrich_transcription

    episode_context = get_episode_context(db_path, result.get("episode_id"))
    episode_text = (
        (episode_context or {}).get("clean_text")
        or (episode_context or {}).get("raw_text")
        or enrichment_text
    )
    _enrich_t0 = _time.monotonic()
    event = enrich_transcription(
        transcription_id=transcription_id,
        episode_id=result.get("episode_id"),
        text=episode_text,
        timestamp=datetime.now(),
        duration_sec=_episode_duration_seconds(episode_context, result.get("duration", 0.0) or 0.0),
        language=result.get("language", "unknown") or "unknown",
        acoustic_metadata=acoustic_metadata,
    )
    _enrich_latency_ms = int((_time.monotonic() - _enrich_t0) * 1000)
    persist_structured_event(db_path, event)
    episode_id = refresh_episode_from_event(db_path, transcription_id, event)
    if episode_id:
        result["episode_id"] = episode_id
        truth = _apply_episode_truth_gate(
            db_path,
            result.get("ingest_id", transcription_id),
            transcription_id,
            episode_id,
            source="gate",
        )
        if truth:
            result["quality_state"] = truth["quality_state"]
            result["quality_score"] = truth["quality_score"]
            result["quality_reasons_json"] = truth["quality_reasons_json"]
            result["needs_recheck"] = truth["needs_recheck"]
    log_event(
        result.get("ingest_id", transcription_id),
        STAGE_ENRICHED,
        latency_ms=_enrich_latency_ms,
        details={
            "model": getattr(event, "enrichment_model", ""),
            "tokens": getattr(event, "enrichment_tokens", 0),
            "transcription_id": transcription_id,
            "episode_id": episode_id or result.get("episode_id"),
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
    segment_id: str | None = None,
    captured_at: str | None = None,
    queue_status: str = "pending",
) -> dict[str, Any]:
    """Persist WAV file and queue row, append integrity event.

    Returns artifact metadata used by handlers.
    """
    validate_upload_payload(content, content_type)

    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_ingest_tables(db_path)
    ensure_integrity_tables(db_path)
    existing = get_existing_ingest(db_path, segment_id=segment_id)
    if existing:
        try:
            db = get_reflexio_db(db_path)
            with db.transaction():
                db.execute(
                    "UPDATE ingest_queue SET transport_status='deduplicated' WHERE id=?",
                    (existing["id"],),
                )
        except Exception as e:
            logger.warning("ingest_deduplicate_mark_failed", ingest_id=existing["id"], error=str(e))
        return {
            "ingest_id": existing["id"],
            "filename": existing["filename"],
            "dest_path": Path(existing["file_path"]),
            "db_path": db_path,
            "size": existing["file_size"],
            "duplicate": True,
            "existing_status": existing["status"],
            "existing_result": get_transcription_by_ingest_id(db_path, existing["id"]),
        }

    ingest_id = file_id or str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{ingest_id}.wav"
    dest_path = settings.UPLOADS_PATH / filename
    settings.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(content)

    audio_sha256 = hashlib.sha256(content).hexdigest()

    try:
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT OR REPLACE INTO ingest_queue (
                    id, segment_id, filename, file_path, file_size, status,
                    transport_status, processing_status, captured_at, audio_sha256,
                    created_at, processed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'received', ?, ?, ?, ?, COALESCE((SELECT processed_at FROM ingest_queue WHERE id=?), NULL))
                """,
                (
                    ingest_id,
                    segment_id,
                    filename,
                    str(dest_path),
                    len(content),
                    queue_status,
                    queue_status,
                    captured_at,
                    audio_sha256,
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
        "duplicate": False,
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
        precheck_ok, precheck_reason = _precheck_audio_artifact(file_path)
        if not precheck_ok:
            terminal_status = "quarantined" if precheck_reason == "invalid_wav" else "filtered"
            _mark_ingest_status(
                db_path,
                ingest_id,
                terminal_status,
                precheck_reason,
                processing_status=terminal_status,
                error_code=precheck_reason,
                quarantine_reason=precheck_reason if terminal_status == "quarantined" else None,
            )
            if delete_audio_after:
                file_path.unlink(missing_ok=True)
            return {
                "status": terminal_status,
                "reason": precheck_reason,
                "ingest_id": ingest_id,
                "filename": filename,
            }

        _mark_ingest_status(
            db_path,
            ingest_id,
            "asr_pending",
            transport_status="server_acked",
            processing_status="asr_pending",
        )
        allowed_speech, speech_reason = _check_speech_gate(file_path)
        if not allowed_speech:
            _mark_ingest_status(
                db_path,
                ingest_id,
                "filtered",
                speech_reason,
                transport_status="server_acked",
                processing_status="filtered",
                error_code="speech_gate_filtered",
            )
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
                # ПОЧЕМУ сохраняем в контексте: speaker data нужна в persist_ws_transcription
                speaker_data = {
                    "speaker_confidence": verification.confidence,
                    "is_user": verification.is_user,
                    "speaker_id": verification.speaker_id,
                }
                if not verification.is_user:
                    _mark_ingest_status(
                        db_path,
                        ingest_id,
                        "filtered",
                        "not_user_speaker",
                        transport_status="server_acked",
                        processing_status="filtered",
                        error_code="speaker_filtered",
                    )
                    if delete_audio_after:
                        file_path.unlink(missing_ok=True)
                    return {
                        "status": "filtered",
                        "reason": "not_user_speaker",
                        "ingest_id": ingest_id,
                        "filename": filename,
                        "speaker_confidence": verification.confidence,
                    }
            else:
                speaker_data = None
        else:
            speaker_data = None

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
            _mark_ingest_status(
                db_path,
                ingest_id,
                "filtered",
                f"unsupported_language:{detected_lang or 'unknown'}",
                transport_status="server_acked",
                processing_status="filtered",
                error_code="unsupported_language",
            )
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
            _mark_ingest_status(
                db_path,
                ingest_id,
                "filtered",
                "noise",
                transport_status="server_acked",
                processing_status="filtered",
                error_code="noise",
            )
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
            _mark_ingest_status(
                db_path,
                ingest_id,
                "filtered",
                "pii_blocked",
                transport_status="server_acked",
                processing_status="filtered",
                error_code="pii_blocked",
            )
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
        result["transcript_raw"] = text
        result["transcript_clean"] = privacy.text
        result["asr_model"] = settings.ASR_MODEL_SIZE
        result["asr_confidence"] = lang_prob
        quality_score, needs_recheck, garbage_flag = _assess_transcription_quality(result)
        result["quality_score"] = quality_score
        result["needs_recheck"] = needs_recheck
        result["garbage_flag"] = garbage_flag
        # ПОЧЕМУ speaker_data в result: persist_ws_transcription сохранит is_user/confidence в БД
        if speaker_data:
            result["speaker_confidence"] = speaker_data["speaker_confidence"]
            result["is_user"] = speaker_data["is_user"]
            result["speaker_id"] = speaker_data["speaker_id"]

        transcription_id = persist_ws_transcription(
            db_path=db_path,
            file_id=ingest_id,
            filename=filename,
            file_path=str(file_path),
            file_size=file_size,
            result=result,
        )
        episode_id = attach_transcription_to_episode(db_path, transcription_id) if transcription_id else None
        if episode_id:
            result["episode_id"] = episode_id

        if transcription_id:
            flagged, quarantine_reason, penalty = _assess_contextual_transcription_risk(
                db_path, transcription_id, episode_id, result
            )
            if flagged:
                quality_score = max(0.0, min(result["quality_score"], result["quality_score"] - penalty))
                result["quality_score"] = quality_score
                result["needs_recheck"] = True
                result["garbage_flag"] = True
                _mark_transcription_for_review(db_path, transcription_id, episode_id, quality_score)
                _mark_ingest_status(
                    db_path,
                    ingest_id,
                    "quarantined",
                    quarantine_reason,
                    transport_status="server_acked",
                    processing_status="quarantined",
                    error_code=quarantine_reason,
                    quarantine_reason=quarantine_reason,
                    quality_score=quality_score,
                    needs_recheck=True,
                )
                if delete_audio_after:
                    file_path.unlink(missing_ok=True)
                logger.warning(
                    "transcription_quarantined_by_context_qc",
                    ingest_id=ingest_id,
                    transcription_id=transcription_id,
                    episode_id=episode_id,
                    reason=quarantine_reason,
                )
                return {
                    "status": "quarantined",
                    "reason": quarantine_reason,
                    "ingest_id": ingest_id,
                    "filename": filename,
                    "transcription_id": transcription_id,
                    "result": result,
                }

        truth = _apply_episode_truth_gate(
            db_path,
            ingest_id,
            transcription_id,
            episode_id,
            source="gate",
        )
        if truth:
            result["quality_state"] = truth["quality_state"]
            result["quality_score"] = truth["quality_score"]
            result["quality_reasons_json"] = truth["quality_reasons_json"]
            result["needs_recheck"] = truth["needs_recheck"]
            quality_score = truth["quality_score"]
            needs_recheck = truth["needs_recheck"]
            if truth["quality_state"] == "quarantined":
                if delete_audio_after:
                    file_path.unlink(missing_ok=True)
                return {
                    "status": "quarantined",
                    "reason": "episode_quality_quarantined",
                    "ingest_id": ingest_id,
                    "filename": filename,
                    "transcription_id": transcription_id,
                    "result": result,
                }
            if truth["quality_state"] == "garbage":
                if delete_audio_after:
                    file_path.unlink(missing_ok=True)
                return {
                    "status": "filtered",
                    "reason": "episode_quality_garbage",
                    "ingest_id": ingest_id,
                    "filename": filename,
                    "transcription_id": transcription_id,
                    "result": result,
                }

        if settings.INTEGRITY_CHAIN_ENABLED:
            append_integrity_event(
                db_path=db_path,
                ingest_id=ingest_id,
                stage=transcription_stage,
                payload_text=result.get("text", ""),
                metadata={"language": result.get("language", ""), "privacy_mode": privacy.mode},
            )

        _mark_ingest_status(
            db_path,
            ingest_id,
            "transcribed",
            transport_status="server_acked",
            processing_status="transcribed",
            quality_score=quality_score,
            needs_recheck=needs_recheck,
        )
        _asr_latency_ms = int((_time.monotonic() - _asr_t0) * 1000)
        log_event(
            ingest_id,
            STAGE_ASR_DONE,
            latency_ms=_asr_latency_ms,
            details={
                "words": len(text.split()),
                "lang": detected_lang,
                "transcription_id": transcription_id,
            },
        )
        if delete_audio_after:
            file_path.unlink(missing_ok=True)

        if run_enrichment and transcription_id:
            text_for_enrichment = (
                f"{(enrichment_prefix or '').strip()} {result.get('text', '').strip()}".strip()
            )
            _mark_ingest_status(
                db_path,
                ingest_id,
                "event_pending",
                transport_status="server_acked",
                processing_status="event_pending",
                quality_score=quality_score,
                needs_recheck=needs_recheck,
            )
            try:
                _run_enrichment_sync(
                    db_path=db_path,
                    transcription_id=transcription_id,
                    result=result,
                    enrichment_text=text_for_enrichment,
                    acoustic_metadata=acoustic_metadata,
                )
                _mark_ingest_status(
                    db_path,
                    ingest_id,
                    "event_ready",
                    transport_status="server_acked",
                    processing_status="event_ready",
                    quality_score=quality_score,
                    needs_recheck=needs_recheck,
                )
            except Exception as enrich_error:
                logger.warning(
                    "enrichment_degraded_after_transcription",
                    ingest_id=ingest_id,
                    error=str(enrich_error),
                )
                _mark_ingest_status(
                    db_path,
                    ingest_id,
                    "transcribed",
                    str(enrich_error),
                    transport_status="server_acked",
                    processing_status="transcribed",
                    error_code="enrichment_failed",
                    quality_score=quality_score,
                    needs_recheck=needs_recheck,
                )

        return {
            "status": "transcribed",
            "ingest_id": ingest_id,
            "filename": filename,
            "transcription_id": transcription_id,
            "result": result,
        }
    except Exception as e:
        _mark_ingest_status(
            db_path,
            ingest_id,
            "retryable_error",
            str(e),
            transport_status="server_acked",
            processing_status="asr_pending",
            error_code="asr_runtime_error",
        )
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
    segment_id: str | None = None,
    captured_at: str | None = None,
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
        segment_id=segment_id,
        captured_at=captured_at,
        queue_status="pending",
    )
    db_path = artifact["db_path"]
    dest_path = artifact["dest_path"]
    ingest_id = artifact["ingest_id"]
    filename = artifact["filename"]

    if artifact.get("duplicate"):
        return {
            "status": "duplicate",
            "ingest_id": ingest_id,
            "filename": filename,
            "result": artifact.get("existing_result"),
        }

    ensure_ingest_tables(db_path)
    ensure_integrity_tables(db_path)
    ensure_semantic_memory_tables(db_path)
    ensure_speaker_tables(db_path)

    if not transcribe_now:
        _mark_ingest_status(
            db_path,
            ingest_id,
            "received",
            transport_status="server_acked",
            processing_status="received",
        )
        return {
            "status": "received",
            "ingest_id": ingest_id,
            "filename": filename,
        }

    try:
        precheck_ok, precheck_reason = _precheck_audio_artifact(dest_path)
        if not precheck_ok:
            terminal_status = "quarantined" if precheck_reason == "invalid_wav" else "filtered"
            _mark_ingest_status(
                db_path,
                ingest_id,
                terminal_status,
                precheck_reason,
                transport_status="server_acked",
                processing_status=terminal_status,
                error_code=precheck_reason,
                quarantine_reason=precheck_reason if terminal_status == "quarantined" else None,
            )
            if delete_audio_after:
                dest_path.unlink(missing_ok=True)
            return {
                "status": terminal_status,
                "reason": precheck_reason,
                "ingest_id": ingest_id,
                "filename": filename,
            }

        _mark_ingest_status(
            db_path,
            ingest_id,
            "asr_pending",
            transport_status="server_acked",
            processing_status="asr_pending",
        )
        allowed_speech, speech_reason = _check_speech_gate(dest_path)
        if not allowed_speech:
            _mark_ingest_status(
                db_path,
                ingest_id,
                "filtered",
                speech_reason,
                transport_status="server_acked",
                processing_status="filtered",
                error_code="speech_gate_filtered",
            )
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
                speaker_data = {
                    "speaker_confidence": verification.confidence,
                    "is_user": verification.is_user,
                    "speaker_id": verification.speaker_id,
                }
                if not verification.is_user:
                    _mark_ingest_status(
                        db_path,
                        ingest_id,
                        "filtered",
                        "not_user_speaker",
                        transport_status="server_acked",
                        processing_status="filtered",
                        error_code="speaker_filtered",
                    )
                    if delete_audio_after:
                        dest_path.unlink(missing_ok=True)
                    return {
                        "status": "filtered",
                        "reason": "not_user_speaker",
                        "ingest_id": ingest_id,
                        "filename": filename,
                        "speaker_confidence": verification.confidence,
                    }
            else:
                speaker_data = None
        else:
            speaker_data = None

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
            _mark_ingest_status(
                db_path,
                ingest_id,
                "filtered",
                f"unsupported_language:{detected_lang or 'unknown'}",
                transport_status="server_acked",
                processing_status="filtered",
                error_code="unsupported_language",
            )
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
            _mark_ingest_status(
                db_path,
                ingest_id,
                "filtered",
                "noise",
                transport_status="server_acked",
                processing_status="filtered",
                error_code="noise",
            )
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
            _mark_ingest_status(
                db_path,
                ingest_id,
                "filtered",
                "pii_blocked",
                transport_status="server_acked",
                processing_status="filtered",
                error_code="pii_blocked",
            )
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
        result["transcript_raw"] = text
        result["transcript_clean"] = privacy.text
        result["asr_model"] = settings.ASR_MODEL_SIZE
        result["asr_confidence"] = lang_prob
        quality_score, needs_recheck, garbage_flag = _assess_transcription_quality(result)
        result["quality_score"] = quality_score
        result["needs_recheck"] = needs_recheck
        result["garbage_flag"] = garbage_flag
        if speaker_data:
            result["speaker_confidence"] = speaker_data["speaker_confidence"]
            result["is_user"] = speaker_data["is_user"]
            result["speaker_id"] = speaker_data["speaker_id"]

        transcription_id = persist_ws_transcription(
            db_path=db_path,
            file_id=ingest_id,
            filename=filename,
            file_path=str(dest_path),
            file_size=len(content),
            result=result,
        )
        episode_id = attach_transcription_to_episode(db_path, transcription_id) if transcription_id else None
        if episode_id:
            result["episode_id"] = episode_id

        if transcription_id:
            flagged, quarantine_reason, penalty = _assess_contextual_transcription_risk(
                db_path, transcription_id, episode_id, result
            )
            if flagged:
                quality_score = max(0.0, min(result["quality_score"], result["quality_score"] - penalty))
                result["quality_score"] = quality_score
                result["needs_recheck"] = True
                result["garbage_flag"] = True
                _mark_transcription_for_review(db_path, transcription_id, episode_id, quality_score)
                _mark_ingest_status(
                    db_path,
                    ingest_id,
                    "quarantined",
                    quarantine_reason,
                    transport_status="server_acked",
                    processing_status="quarantined",
                    error_code=quarantine_reason,
                    quarantine_reason=quarantine_reason,
                    quality_score=quality_score,
                    needs_recheck=True,
                )
                if delete_audio_after:
                    dest_path.unlink(missing_ok=True)
                logger.warning(
                    "transcription_quarantined_by_context_qc",
                    ingest_id=ingest_id,
                    transcription_id=transcription_id,
                    episode_id=episode_id,
                    reason=quarantine_reason,
                )
                return {
                    "status": "quarantined",
                    "reason": quarantine_reason,
                    "ingest_id": ingest_id,
                    "filename": filename,
                    "transcription_id": transcription_id,
                    "result": result,
                }

        truth = _apply_episode_truth_gate(
            db_path,
            ingest_id,
            transcription_id,
            episode_id,
            source="gate",
        )
        if truth:
            result["quality_state"] = truth["quality_state"]
            result["quality_score"] = truth["quality_score"]
            result["quality_reasons_json"] = truth["quality_reasons_json"]
            result["needs_recheck"] = truth["needs_recheck"]
            quality_score = truth["quality_score"]
            needs_recheck = truth["needs_recheck"]
            if truth["quality_state"] == "quarantined":
                if delete_audio_after:
                    dest_path.unlink(missing_ok=True)
                return {
                    "status": "quarantined",
                    "reason": "episode_quality_quarantined",
                    "ingest_id": ingest_id,
                    "filename": filename,
                    "transcription_id": transcription_id,
                    "result": result,
                }
            if truth["quality_state"] == "garbage":
                if delete_audio_after:
                    dest_path.unlink(missing_ok=True)
                return {
                    "status": "filtered",
                    "reason": "episode_quality_garbage",
                    "ingest_id": ingest_id,
                    "filename": filename,
                    "transcription_id": transcription_id,
                    "result": result,
                }

        if settings.INTEGRITY_CHAIN_ENABLED:
            append_integrity_event(
                db_path=db_path,
                ingest_id=ingest_id,
                stage=transcription_stage,
                payload_text=result.get("text", ""),
                metadata={"language": result.get("language", ""), "privacy_mode": privacy.mode},
            )

        _mark_ingest_status(
            db_path,
            ingest_id,
            "transcribed",
            transport_status="server_acked",
            processing_status="transcribed",
            quality_score=quality_score,
            needs_recheck=needs_recheck,
        )
        log_event(
            ingest_id,
            STAGE_ASR_DONE,
            latency_ms=_asr_latency_ms,
            details={
                "words": len(text.split()),
                "lang": detected_lang,
                "transcription_id": transcription_id,
                "episode_id": episode_id,
            },
        )
        if delete_audio_after:
            dest_path.unlink(missing_ok=True)

        if run_enrichment and transcription_id:
            text_for_enrichment = (
                enrichment_text
                or f"{(enrichment_prefix or '').strip()} {result.get('text', '').strip()}".strip()
            )
            from src.enrichment.worker import get_enrichment_worker, EnrichmentTask

            worker = get_enrichment_worker()
            _mark_ingest_status(
                db_path,
                ingest_id,
                "event_pending",
                transport_status="server_acked",
                processing_status="event_pending",
                quality_score=quality_score,
                needs_recheck=needs_recheck,
            )
            await worker.submit(
                EnrichmentTask(
                    db_path=db_path,
                    transcription_id=transcription_id,
                    result=result,
                    enrichment_text=text_for_enrichment,
                    acoustic_metadata=acoustic_metadata,
                )
            )

        return {
            "status": "transcribed",
            "ingest_id": ingest_id,
            "filename": filename,
            "transcription_id": transcription_id,
            "episode_id": episode_id,
            "result": result,
        }
    except Exception as e:
        _mark_ingest_status(
            db_path,
            ingest_id,
            "retryable_error",
            "processing_failed",
            transport_status="server_acked",
            processing_status="asr_pending",
            error_code="asr_runtime_error",
        )
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
