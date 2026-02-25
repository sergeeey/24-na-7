"""Быстрый амплитудный gate (Уровень 1 верификации спикера).

ПОЧЕМУ отдельный модуль:
- RMS вычисляется за ~0.1ms (vs embedder ~50ms)
- Тихие сегменты (тишина, шорох) дадут шумовой embedding — бессмысленно проверять
- Разделение ответственности: amplitude.py не знает про resemblyzer
"""
from __future__ import annotations

import numpy as np


def compute_rms(audio: np.ndarray) -> float:
    """Среднеквадратичная амплитуда аудио-сигнала (float32, нормализованный [-1, 1])."""
    if len(audio) == 0:
        return 0.0
    # ПОЧЕМУ float64: накопление ошибок при суммировании большого числа float32 элементов
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


def passes_amplitude_gate(audio: np.ndarray, threshold: float = 0.01) -> bool:
    """Проверяет, достаточно ли громкий сигнал для анализа embedding.

    Args:
        audio: float32 [-1, 1], sample rate 16kHz
        threshold: минимальный RMS. 0.01 = ~-40dBFS (тихий, но речь слышна)

    Returns:
        True — сигнал достаточно громкий, можно считать embedding
        False — слишком тихо, пропускаем embedding (считаем not_user)
    """
    return compute_rms(audio) >= threshold
