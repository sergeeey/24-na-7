"""
Enricher — обогащает транскрипцию в StructuredEvent через LLM.

ПОЧЕМУ обёртка, а не прямой вызов: analyze_recording_text() возвращает
сырой dict. Enricher добавляет метаданные (ASR confidence, latency,
модель) и упаковывает в Pydantic-валидированный StructuredEvent.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Optional

from src.utils.logging import get_logger
from src.enrichment.schema import StructuredEvent, TaskExtracted

logger = get_logger("enrichment")

# ПОЧЕМУ: фильтруем Whisper-галлюцинации ДО вызова LLM (экономия токенов)
WHISPER_HALLUCINATIONS = {
    "", "thank you", "thank you.", "thank you very much.",
    "thanks.", "you", "bye.", "bye",
    "thanks for watching!", "subscribe",
}

# Минимум слов для enrichment (короче — не стоит тратить LLM-токены)
MIN_WORDS_FOR_ENRICHMENT = 3


def enrich_transcription(
    transcription_id: str,
    text: str,
    timestamp: datetime,
    duration_sec: float = 0.0,
    language: str = "unknown",
    asr_confidence: float = 0.0,
) -> StructuredEvent:
    """
    Обогащает транскрипцию в StructuredEvent.

    Если текст слишком короткий или похож на галлюцинацию —
    возвращает event с пустыми полями enrichment (graceful degradation).
    """
    event_id = str(uuid.uuid4())
    now = datetime.utcnow()

    # Базовый event без enrichment
    base_event = StructuredEvent(
        id=event_id,
        transcription_id=transcription_id,
        timestamp=timestamp,
        duration_sec=duration_sec,
        text=text,
        language=language,
        asr_confidence=asr_confidence,
        created_at=now,
    )

    # Фильтр: пустой текст, галлюцинации, слишком короткий
    clean_text = text.strip()
    if not clean_text:
        logger.debug("enrichment_skipped", reason="empty_text")
        return base_event

    if clean_text.lower().rstrip(".!?") in WHISPER_HALLUCINATIONS:
        logger.info("enrichment_skipped", reason="whisper_hallucination", text=clean_text)
        return base_event

    if len(clean_text.split()) < MIN_WORDS_FOR_ENRICHMENT:
        logger.debug("enrichment_skipped", reason="too_short", words=len(clean_text.split()))
        return base_event

    # LLM enrichment
    try:
        from src.summarizer.few_shot import analyze_recording_text

        start = time.time()
        analysis = analyze_recording_text(clean_text)
        latency_ms = (time.time() - start) * 1000

        # Упаковываем tasks
        tasks = []
        for action in analysis.get("actions", []):
            if isinstance(action, str) and action.strip():
                tasks.append(TaskExtracted(text=action.strip()))
            elif isinstance(action, dict) and action.get("text"):
                tasks.append(TaskExtracted(
                    text=action["text"],
                    priority=action.get("priority", "medium"),
                    deadline=action.get("deadline"),
                ))

        # Определяем sentiment из emotions
        positive_emotions = {"радость", "оптимизм", "уверенность", "воодушевление", "счастье"}
        negative_emotions = {"грусть", "злость", "тревога", "страх", "разочарование"}
        emotions = analysis.get("emotions", [])
        sentiment = "neutral"
        if any(e.lower() in positive_emotions for e in emotions):
            sentiment = "positive"
        elif any(e.lower() in negative_emotions for e in emotions):
            sentiment = "negative"

        # Получаем имя модели
        try:
            from src.utils.config import settings
            model_name = getattr(settings, "LLM_MODEL_ACTOR", "unknown")
        except Exception:
            model_name = "unknown"

        base_event.summary = analysis.get("summary", "")
        base_event.emotions = emotions
        base_event.topics = analysis.get("topics", [])
        base_event.tasks = tasks
        base_event.urgency = analysis.get("urgency", "medium")
        base_event.sentiment = sentiment
        base_event.enrichment_confidence = 0.8
        base_event.enrichment_model = model_name
        base_event.enrichment_latency_ms = round(latency_ms, 2)

        logger.info(
            "enrichment_complete",
            event_id=event_id,
            topics=base_event.topics,
            tasks_count=len(tasks),
            latency_ms=round(latency_ms),
        )

    except Exception as e:
        logger.warning("enrichment_failed", error=str(e), event_id=event_id)
        # Graceful degradation — event сохранится с пустыми полями enrichment

    return base_event
