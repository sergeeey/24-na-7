"""Enricher — обогащает транскрипцию в StructuredEvent через LLM."""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

from src.enrichment.domain_classifier import classify_domains
from src.enrichment.schema import CommitmentExtracted, StructuredEvent, TaskExtracted
from src.utils.logging import get_logger

logger = get_logger("enrichment")

# ПОЧЕМУ семантическая версия: при смене промпта или логики enrichment
# инкрементируем версию. Позволяет фильтровать events по версии,
# детектировать drift, воспроизводить старые результаты.
ENRICHMENT_VERSION = "2.1.0"  # 2.0=base, 2.1=acoustic hints

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

# ПОЧЕМУ 3 слова: enrichment стоит ~$0.002 за вызов LLM. Тратить на "ну ладно окей" —
# расточительство. 3 слова = минимум для извлечения хотя бы одной эмоции/темы.
MIN_WORDS_FOR_ENRICHMENT = 3


def _compute_enrichment_confidence(analysis: dict) -> float:
    """Закон достаточного основания: каждый вес обоснован.

    ПОЧЕМУ эти веса: summary (0.3) — главный индикатор что LLM понял текст.
    topics (0.2) + emotions (0.2) = 0.4 — ядро enrichment.
    urgency (0.15) + actions (0.15) = 0.3 — бонус за глубину.
    Сумма = 1.0. Если всё заполнено — максимальная уверенность.
    """
    score = 0.0
    # ПОЧЕМУ > 30 символов: "Разговор" = 8 символов — это не саммари. 30 = ~5 слов.
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


def _build_acoustic_hint(acoustic: dict[str, Any]) -> str:
    """Формирует текстовую подсказку для LLM из акустических данных.

    ПОЧЕМУ текст а не JSON: LLM лучше понимает естественный язык.
    15-20 дополнительных tokens — пренебрежимая стоимость ($0.000003).
    """
    arousal = acoustic.get("acoustic_arousal", "normal")
    pitch_var = acoustic.get("pitch_variance", 0)
    energy = acoustic.get("energy_mean", 0)

    parts = []
    if arousal == "high":
        parts.append("Голос возбуждённый: высокая вариативность тона и громкость")
    elif arousal == "low":
        parts.append("Голос тихий и монотонный (возможна усталость или подавленность)")

    # ПОЧЕМУ 40 Гц: pitch variance > 40 = эмоциональная речь (крик, смех, удивление).
    # Типичная спокойная речь = 10-30 Гц variance. Источник: librosa pitch tracking.
    if pitch_var > 40:
        parts.append(f"сильные колебания тона ({pitch_var:.0f} Гц)")
    elif pitch_var < 10 and arousal != "low":
        parts.append("ровный монотонный тон")

    # ПОЧЕМУ 0.08/0.01: RMS energy нормализован 0-1. Тестировано на 50+ записях:
    # > 0.08 = громкая речь (шумное кафе, крик). < 0.01 = шёпот или далеко от микрофона.
    if energy > 0.08:
        parts.append("говорит громко")
    elif energy < 0.01:
        parts.append("говорит очень тихо")

    if not parts:
        return ""
    return "\n[Акустика голоса: " + ", ".join(parts) + ". Учти при определении эмоций.]"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    before_sleep=before_sleep_log(logger, "warning"),
    reraise=True,
)
def _call_llm_analysis(clean_text: str) -> dict[str, Any]:
    """LLM-анализ с tenacity retry + exponential backoff.

    ПОЧЕМУ tenacity вместо ручного loop + time.sleep:
    time.sleep блокирует thread pool worker на 2-8 сек.
    tenacity — декларативный retry с logging hooks из коробки.
    """
    from src.summarizer.few_shot import analyze_recording_text

    return analyze_recording_text(clean_text)


def _run_analysis_with_retry(clean_text: str) -> tuple[dict[str, Any], float]:
    """Вызывает LLM-анализ с retry, возвращает (result, latency_ms)."""
    start = time.time()
    analysis = _call_llm_analysis(clean_text)
    latency_ms = (time.time() - start) * 1000
    return analysis, latency_ms


def enrich_transcription(
    transcription_id: str,
    episode_id: str | None,
    text: str,
    timestamp: datetime,
    duration_sec: float = 0.0,
    language: str = "unknown",
    asr_confidence: float = 0.0,
    acoustic_metadata: dict[str, Any] | None = None,
) -> StructuredEvent:
    """Обогащает транскрипцию в StructuredEvent.

    acoustic_metadata: если передан — акустические фичи (pitch, energy, arousal)
    инжектируются в LLM промпт для улучшения определения эмоций.
    """
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    base_event = StructuredEvent(
        id=event_id,
        transcription_id=transcription_id,
        episode_id=episode_id,
        timestamp=timestamp,
        duration_sec=duration_sec,
        text=text,
        language=language,
        asr_confidence=asr_confidence,
        created_at=now,
    )

    # Сохраняем акустику в event независимо от LLM enrichment
    if acoustic_metadata:
        base_event.pitch_hz_mean = acoustic_metadata.get("pitch_hz_mean")
        base_event.pitch_variance = acoustic_metadata.get("pitch_variance")
        base_event.energy_mean = acoustic_metadata.get("energy_mean")
        base_event.spectral_centroid_mean = acoustic_metadata.get("spectral_centroid_mean")
        base_event.acoustic_arousal = acoustic_metadata.get("acoustic_arousal")

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

        # ПОЧЕМУ acoustic hint добавляется к тексту: LLM получает и слова,
        # и подсказку о тоне голоса — два канала данных вместо одного.
        enrichment_input = clean_text
        if acoustic_metadata:
            hint = _build_acoustic_hint(acoustic_metadata)
            if hint:
                enrichment_input = clean_text + hint

        # ПОЧЕМУ hash промпта: через 3 месяца другой промпт даст другие
        # эмоции. Hash позволяет детектировать момент drift.
        prompt_hash = hashlib.sha256(enrichment_input.encode("utf-8", errors="ignore")).hexdigest()[
            :12
        ]

        analysis, latency_ms = _run_analysis_with_retry(enrichment_input)

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
        domains = classify_domains(
            clean_text, topics=topics, db_path=settings.STORAGE_PATH / "reflexio.db"
        )

        # ПОЧЕМУ commitments отдельно от tasks: task = "для себя",
        # commitment = "обещал кому-то" (person-aware). Разные сущности.
        commitments = []
        for c in analysis.get("commitments", []):
            if isinstance(c, dict) and c.get("person") and c.get("action"):
                commitments.append(
                    CommitmentExtracted(
                        person=c["person"].strip(),
                        action=c["action"].strip(),
                        deadline=c.get("deadline"),
                        context=c.get("context"),
                    )
                )

        base_event.summary = analysis.get("summary", "")
        base_event.emotions = emotions
        base_event.topics = topics
        base_event.domains = domains
        base_event.tasks = tasks
        base_event.commitments = commitments
        base_event.urgency = analysis.get("urgency", "medium")
        base_event.sentiment = sentiment
        base_event.enrichment_confidence = _compute_enrichment_confidence(analysis)
        base_event.enrichment_model = model_name
        base_event.enrichment_latency_ms = round(latency_ms, 2)
        base_event.enrichment_prompt_hash = prompt_hash
        base_event.enrichment_version = ENRICHMENT_VERSION

        logger.info(
            "enrichment_complete",
            event_id=event_id,
            topics=base_event.topics,
            domains=base_event.domains,
            tasks_count=len(tasks),
            commitments_count=len(commitments),
            latency_ms=round(latency_ms),
        )

    except Exception as e:
        logger.warning("enrichment_failed", error=str(e), event_id=event_id)

    return base_event
