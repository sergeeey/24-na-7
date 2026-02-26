"""Enricher — обогащает транскрипцию в StructuredEvent через LLM."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from src.enrichment.domain_classifier import classify_domains
from src.enrichment.schema import StructuredEvent, TaskExtracted
from src.utils.logging import get_logger

logger = get_logger("enrichment")

WHISPER_HALLUCINATIONS = {
    "",
    "thank you",
    "thank you.",
    "thank you very much.",
    "thanks.",
    "you",
    "bye.",
    "bye",
    "thanks for watching!",
    "subscribe",
    "спасибо",
    "спасибо.",
    "спасибо за просмотр",
    "спасибо за просмотр.",
    "подписывайтесь",
    "подписывайтесь.",
    "угу",
    "ага",
    "ну",
    "мм",
    "хм",
    "ладно",
    "окей",
}

MIN_WORDS_FOR_ENRICHMENT = 3
ENRICHMENT_MAX_RETRIES = 3
ENRICHMENT_BACKOFF_SEC = (2, 4, 8)


def _compute_enrichment_confidence(analysis: dict) -> float:
    score = 0.0
    if len((analysis.get("summary") or "").strip()) > 30:
        score += 0.3
    if len(analysis.get("topics") or []) >= 2:
        score += 0.2
    if len(analysis.get("emotions") or []) >= 1:
        score += 0.2
    if (analysis.get("urgency") or "medium") != "medium":
        score += 0.15
    if len(analysis.get("actions") or []) >= 1:
        score += 0.15
    return round(min(score, 1.0), 2)


def _run_analysis_with_retry(clean_text: str) -> tuple[dict[str, Any], float]:
    """Вызывает LLM-анализ с retry + exponential backoff."""
    from src.summarizer.few_shot import analyze_recording_text

    last_error: Exception | None = None
    for attempt in range(ENRICHMENT_MAX_RETRIES):
        try:
            start = time.time()
            analysis = analyze_recording_text(clean_text)
            latency_ms = (time.time() - start) * 1000
            return analysis, latency_ms
        except Exception as e:
            last_error = e
            wait_s = ENRICHMENT_BACKOFF_SEC[min(attempt, len(ENRICHMENT_BACKOFF_SEC) - 1)]
            logger.warning(
                "enrichment_attempt_failed",
                attempt=attempt + 1,
                max_attempts=ENRICHMENT_MAX_RETRIES,
                backoff_sec=wait_s,
                error=str(e),
            )
            if attempt < ENRICHMENT_MAX_RETRIES - 1:
                time.sleep(wait_s)

    if last_error:
        raise last_error
    raise RuntimeError("Unknown enrichment failure")


def enrich_transcription(
    transcription_id: str,
    text: str,
    timestamp: datetime,
    duration_sec: float = 0.0,
    language: str = "unknown",
    asr_confidence: float = 0.0,
) -> StructuredEvent:
    """Обогащает транскрипцию в StructuredEvent."""
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

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

    clean_text = text.strip()
    if not clean_text:
        logger.debug("enrichment_skipped", reason="empty_text")
        return base_event

    normalized = clean_text.lower().rstrip(".!?")
    if normalized in WHISPER_HALLUCINATIONS:
        logger.info("enrichment_skipped", reason="whisper_hallucination", text=clean_text)
        return base_event

    if len(clean_text.split()) < MIN_WORDS_FOR_ENRICHMENT:
        logger.debug("enrichment_skipped", reason="too_short", words=len(clean_text.split()))
        return base_event

    try:
        from src.utils.config import settings

        analysis, latency_ms = _run_analysis_with_retry(clean_text)

        tasks = []
        for action in analysis.get("actions", []):
            if isinstance(action, str) and action.strip():
                tasks.append(TaskExtracted(text=action.strip()))
            elif isinstance(action, dict) and action.get("text"):
                tasks.append(
                    TaskExtracted(
                        text=action["text"],
                        priority=action.get("priority", "medium"),
                        deadline=action.get("deadline"),
                    )
                )

        positive_emotions = {"радость", "оптимизм", "уверенность", "воодушевление", "счастье"}
        negative_emotions = {"грусть", "злость", "тревога", "страх", "разочарование"}
        emotions = analysis.get("emotions", [])
        sentiment = "neutral"
        if any(e.lower() in positive_emotions for e in emotions):
            sentiment = "positive"
        elif any(e.lower() in negative_emotions for e in emotions):
            sentiment = "negative"

        model_name = getattr(settings, "LLM_MODEL_ACTOR", "unknown")
        topics = analysis.get("topics", [])
        domains = classify_domains(clean_text, topics=topics, db_path=settings.STORAGE_PATH / "reflexio.db")

        base_event.summary = analysis.get("summary", "")
        base_event.emotions = emotions
        base_event.topics = topics
        base_event.domains = domains
        base_event.tasks = tasks
        base_event.urgency = analysis.get("urgency", "medium")
        base_event.sentiment = sentiment
        base_event.enrichment_confidence = _compute_enrichment_confidence(analysis)
        base_event.enrichment_model = model_name
        base_event.enrichment_latency_ms = round(latency_ms, 2)

        logger.info(
            "enrichment_complete",
            event_id=event_id,
            topics=base_event.topics,
            domains=base_event.domains,
            tasks_count=len(tasks),
            latency_ms=round(latency_ms),
        )

    except Exception as e:
        logger.warning("enrichment_failed", error=str(e), event_id=event_id)

    return base_event

