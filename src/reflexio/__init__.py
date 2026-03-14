"""
Пакет reflexio: захват аудио и транскрипция (интеграция из Golos).
"""
from .audio import AudioRecorder, VADetector, AudioBuffer
from .transcription import WhisperEngine

__all__ = ["AudioRecorder", "WhisperEngine", "VADetector", "AudioBuffer"]
