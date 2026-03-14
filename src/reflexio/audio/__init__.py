"""
Модуль захвата и обработки аудио.
Интеграция из Golos: capture, VAD, buffer.
"""
from .buffer import AudioBuffer
from .capture import AudioRecorder
from .vad import VADetector

__all__ = ["AudioRecorder", "VADetector", "AudioBuffer"]
