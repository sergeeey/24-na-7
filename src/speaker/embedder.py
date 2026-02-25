"""Singleton-обёртка над resemblyzer VoiceEncoder.

ПОЧЕМУ singleton с lock:
- VoiceEncoder загружает LSTM-модель (~18MB) при первом обращении
- Создавать инстанс на каждый запрос = +200ms cold start
- threading.Lock гарантирует единственную инициализацию при параллельных запросах
"""
from __future__ import annotations

import threading

import numpy as np

from src.utils.logging import get_logger

logger = get_logger("speaker.embedder")

_lock = threading.Lock()
_encoder = None  # Lazy init: создаётся при первом вызове get_encoder()


def get_encoder():
    """Возвращает singleton VoiceEncoder (resemblyzer GE2E LSTM).

    Thread-safe: double-checked locking pattern.
    """
    global _encoder
    if _encoder is None:
        with _lock:
            if _encoder is None:
                try:
                    from resemblyzer import VoiceEncoder  # type: ignore[import]

                    _encoder = VoiceEncoder()
                    logger.info("voice_encoder_loaded", model="resemblyzer_GE2E")
                except ImportError as e:
                    logger.error("resemblyzer_not_installed", error=str(e))
                    raise RuntimeError(
                        "resemblyzer not installed. Run: pip install resemblyzer>=0.1.1"
                    ) from e
    return _encoder


def embed_audio(audio_float32: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Вычисляет 256-dim d-vector embedding из float32 аудио.

    Args:
        audio_float32: float32 [-1, 1], нормализованный сигнал
        sample_rate:   частота дискретизации (resemblyzer внутри ресемплирует до 16kHz)

    Returns:
        np.ndarray shape (256,) float32 — d-vector (voice embedding)

    ПОЧЕМУ resemblyzer.preprocess_wav:
        - Обрезает тишину по краям (trimming)
        - Нормализует амплитуду
        - Конвертирует sample rate → 16kHz если нужно
    """
    encoder = get_encoder()

    try:
        from resemblyzer import preprocess_wav  # type: ignore[import]

        wav = preprocess_wav(audio_float32, source_sr=sample_rate)
        embedding: np.ndarray = encoder.embed_utterance(wav)
        return embedding.astype(np.float32)
    except Exception as e:
        logger.warning("embed_audio_failed", error=str(e))
        raise
