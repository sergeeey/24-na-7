"""
Пакет reflexio: захват аудио и транскрипция (интеграция из Golos).
"""
from reflexio.audio import AudioRecorder, VADetector, AudioBuffer
from reflexio.transcription import WhisperEngine

__all__ = ["AudioRecorder", "WhisperEngine", "VADetector", "AudioBuffer"]
