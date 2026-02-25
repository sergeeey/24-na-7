"""Утилиты для enrollment — создание голосового профиля из нескольких WAV образцов.

Процесс:
    1. Пользователь присылает 3+ WAV файла с чистой речью (3-10 секунд каждый)
    2. Для каждого файла вычисляем embedding (256-dim d-vector)
    3. Усредняем embeddings → mean embedding = голосовой профиль
    4. Сохраняем в voice_profiles (старый профиль деактивируется)

ПОЧЕМУ минимум 3 образца:
    Один образец подвержен шуму, вариации тембра, акцента.
    3+ образца → стабильный mean embedding, меньше false negatives.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import List

import numpy as np

from src.utils.logging import get_logger

from .embedder import embed_audio
from .storage import save_voice_profile

logger = get_logger("speaker.enrollment")

MIN_SAMPLES = 3  # Минимум WAV файлов для надёжного профиля
MIN_DURATION_SECONDS = 1.5  # Минимальная длительность одного образца


def _load_wav_float32(wav_path: Path) -> tuple[np.ndarray, int]:
    """Читает WAV в float32 [-1, 1] и возвращает (audio, sample_rate)."""
    with wave.open(str(wav_path), "rb") as wf:
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        audio_int16 = np.frombuffer(frames, dtype=np.int16)
    return audio_int16.astype(np.float32) / 32768.0, sample_rate


def enroll_from_wavs(
    wav_paths: List[Path],
    db_path: Path,
    user_id: str = "default",
) -> dict:
    """Создаёт голосовой профиль из списка WAV файлов.

    Args:
        wav_paths: список путей к WAV (минимум MIN_SAMPLES)
        db_path:   путь к SQLite для сохранения профиля
        user_id:   идентификатор пользователя

    Returns:
        {profile_id, user_id, sample_count, mean_confidence}

    Raises:
        ValueError: недостаточно образцов или WAV слишком короткий
    """
    if len(wav_paths) < MIN_SAMPLES:
        raise ValueError(
            f"Need at least {MIN_SAMPLES} voice samples, got {len(wav_paths)}"
        )

    embeddings: List[np.ndarray] = []
    for wav_path in wav_paths:
        try:
            audio, sr = _load_wav_float32(wav_path)
        except Exception as e:
            logger.warning("enrollment_wav_load_failed", path=str(wav_path), error=str(e))
            raise ValueError(f"Cannot read WAV: {wav_path.name}") from e

        # Проверяем длительность
        duration_sec = len(audio) / sr
        if duration_sec < MIN_DURATION_SECONDS:
            raise ValueError(
                f"Sample too short: {wav_path.name} ({duration_sec:.1f}s < {MIN_DURATION_SECONDS}s)"
            )

        try:
            emb = embed_audio(audio, sr)
            embeddings.append(emb)
            logger.debug("enrollment_sample_embedded", path=wav_path.name, duration_sec=round(duration_sec, 1))
        except Exception as e:
            logger.warning("enrollment_embed_failed", path=str(wav_path), error=str(e))
            raise

    # Усреднённый embedding = "средний голос" пользователя
    # ПОЧЕМУ mean: каждый образец немного отличается (громкость, скорость, шум).
    # Mean embedding устойчив к вариациям и даёт лучшее разделение классов.
    mean_emb = np.mean(np.stack(embeddings), axis=0).astype(np.float32)

    profile_id = save_voice_profile(
        db_path=db_path,
        embedding=mean_emb,
        user_id=user_id,
        sample_count=len(embeddings),
    )

    logger.info(
        "enrollment_complete",
        profile_id=profile_id,
        user_id=user_id,
        samples=len(embeddings),
    )

    return {
        "profile_id": profile_id,
        "user_id": user_id,
        "sample_count": len(embeddings),
    }
