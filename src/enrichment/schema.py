"""StructuredEvent — единица цифровой памяти.
Каждый аудио-сегмент -> один StructuredEvent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskExtracted(BaseModel):
    """Задача, извлечённая из речи."""

    text: str
    priority: str = "medium"  # low | medium | high
    deadline: Optional[str] = None


class StructuredEvent(BaseModel):
    """Единица цифровой памяти."""

    id: str
    transcription_id: str

    # Когда
    timestamp: datetime
    duration_sec: float = 0.0

    # Что (из ASR)
    text: str
    language: str = "unknown"

    # Контекст (из LLM enrichment)
    summary: str = ""
    emotions: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    tasks: list[TaskExtracted] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    speakers: list[str] = Field(default_factory=list)
    urgency: str = "medium"  # low | medium | high
    sentiment: str = "neutral"  # positive | neutral | negative

    # Где (null для MVP)
    location: Optional[str] = None

    # Качество
    asr_confidence: float = 0.0
    enrichment_confidence: float = 0.0
    enrichment_model: str = ""
    enrichment_tokens: int = 0
    enrichment_latency_ms: float = 0.0

    created_at: datetime = Field(default_factory=datetime.utcnow)
