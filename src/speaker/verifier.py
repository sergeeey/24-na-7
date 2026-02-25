"""Двухуровневая верификация спикера.

Уровень 1: RMS амплитудный gate (~0.1ms)
    → тишь/шум → is_user=False, method="amplitude_filtered"
    → достаточно громко → переход к уровню 2

Уровень 2: cosine similarity embedding (~50ms)
    → нет профиля → is_user=True (fail-open для новых пользователей)
    → similarity >= threshold → is_user=True
    → similarity < threshold → is_user=False (фоновый спикер, ТВ, радио)

ПОЧЕМУ двухуровневый:
    В типичный рабочий день ~80% сегментов — пользователь.
    Если silence/шум сразу отсекается на уровне 1, тяжёлый inference (~50ms/сегмент)
    запускается только при реальном голосе — значительная экономия CPU.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.utils.logging import get_logger

from .amplitude import passes_amplitude_gate
from .models import VerificationResult
from .storage import load_active_profile_embedding

logger = get_logger("speaker.verifier")


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Косинусное сходство между двумя векторами [-1, 1] → нормировано в [0, 1].

    ПОЧЕМУ косинус, а не евклидово расстояние:
        d-vectors нормированы на гиперсфере → угол между ними = ключевая метрика.
        Косинус инвариантен к масштабу (громкости сигнала).
    """
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def verify_speaker(
    audio: np.ndarray,
    db_path: Path,
    sample_rate: int = 16000,
    amplitude_threshold: float = 0.01,
    similarity_threshold: float = 0.75,
    user_id: str = "default",
) -> VerificationResult:
    """Проверяет, является ли спикер в аудио-сегменте пользователем.

    Args:
        audio:               float32 [-1, 1], 16kHz аудио сегмент (3-5 сек)
        db_path:             путь к SQLite с голосовыми профилями
        sample_rate:         Hz (должен совпадать с реальным SR файла)
        amplitude_threshold: минимальный RMS для Level 2 (~0.01 = -40dBFS)
        similarity_threshold: минимальное cosine similarity (0.75 = хороший баланс)
        user_id:             идентификатор пользователя в voice_profiles

    Returns:
        VerificationResult(is_user, confidence, speaker_id, method)
    """
    # ── Уровень 1: амплитудный gate ─────────────────────────────────────────
    if not passes_amplitude_gate(audio, amplitude_threshold):
        return VerificationResult(
            is_user=False,
            confidence=0.0,
            speaker_id=0,
            method="amplitude_filtered",
        )

    # ── Загрузка профиля пользователя ───────────────────────────────────────
    user_emb = load_active_profile_embedding(db_path, user_id)
    if user_emb is None:
        # ПОЧЕМУ fail-open: пользователь ещё не создал профиль.
        # Лучше пропустить все записи как "пользовательские", чем молча отбросить всё.
        # После создания профиля (POST /voice/enroll) поведение изменится.
        logger.debug("speaker_no_profile_fail_open", user_id=user_id)
        return VerificationResult(
            is_user=True,
            confidence=1.0,
            speaker_id=1,
            method="no_profile",
        )

    # ── Уровень 2: embedding similarity ─────────────────────────────────────
    try:
        from .embedder import embed_audio

        segment_emb = embed_audio(audio, sample_rate)
        similarity = cosine_similarity(segment_emb, user_emb)
        is_user = similarity >= similarity_threshold

        logger.debug(
            "speaker_verified",
            is_user=is_user,
            similarity=round(similarity, 3),
            threshold=similarity_threshold,
        )

        return VerificationResult(
            is_user=is_user,
            confidence=round(similarity, 4),
            speaker_id=1 if is_user else 0,
            method="embedding",
        )
    except Exception as e:
        # ПОЧЕМУ fail-open при ошибке embedding:
        # resemblyzer иногда падает на очень коротких или битых сегментах.
        # Лучше записать транскрипцию, чем потерять важный фрагмент.
        logger.warning("speaker_embedding_failed_fail_open", error=str(e))
        return VerificationResult(
            is_user=True,
            confidence=0.5,
            speaker_id=1,
            method="no_profile",
        )
