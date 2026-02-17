"""
Модуль захвата и обработки аудио.
Интеграция из Golos: capture, VAD, buffer.
"""
from reflexio.audio.capture import AudioRecorder
from reflexio.audio.vad import VADetector
from reflexio.audio.buffer import AudioBuffer

__all__ = ["AudioRecorder", "VADetector", "AudioBuffer"]
