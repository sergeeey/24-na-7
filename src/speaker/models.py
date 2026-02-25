"""Модели данных для speaker verification."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np


@dataclass
class SpeakerProfile:
    """Голосовой профиль пользователя (усреднённый embedding из N образцов)."""

    profile_id: str
    user_id: str
    # ПОЧЕМУ numpy: resemblyzer возвращает np.ndarray(256,) float32 — не сериализуем напрямую.
    # В БД храним как JSON-список, загружаем обратно в ndarray.
    embedding: np.ndarray  # shape (256,), dtype float32
    sample_count: int = 0
    created_at: str = ""


@dataclass
class VerificationResult:
    """Результат проверки: является ли текущий спикер пользователем."""

    is_user: bool
    confidence: float  # cosine similarity [0.0, 1.0]
    speaker_id: int    # 0 = background/unknown, 1 = enrolled user
    method: Literal[
        "disabled",           # SPEAKER_VERIFICATION_ENABLED=False
        "no_profile",         # профиль не создан — fail-open
        "amplitude_filtered", # RMS < threshold — слишком тихо
        "embedding",          # полная проверка через resemblyzer
    ] = "embedding"
