"""
VAD (Voice Activity Detection) на базе WebRTC VAD.
Интеграция из Golos: детекция речи в PCM-кадрах.
"""

from typing import Optional, cast

import webrtcvad  # type: ignore[import-untyped]


class VADetector:
    """Детектор речевой активности."""

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000) -> None:
        """
        Args:
            aggressiveness: 0-3, выше значение — меньше ложных срабатываний.
            sample_rate: Частота дискретизации (8000, 16000, 32000).
        """
        self._vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate

    def is_speech(self, pcm_frame: bytes, sample_rate: Optional[int] = None) -> bool:
        """
        Определяет, содержит ли кадр речь.

        Args:
            pcm_frame: Кадр PCM 16-bit, длина 10/20/30 ms.
            sample_rate: Частота (если None — используется из конструктора).

        Returns:
            True если детектирована речь.
        """
        sr = sample_rate or self.sample_rate
        return cast(bool, self._vad.is_speech(pcm_frame, sr))

    def set_aggressiveness(self, aggressiveness: int) -> None:
        """Устанавливает уровень агрессивности (0-3)."""
        self._vad = webrtcvad.Vad(aggressiveness)
