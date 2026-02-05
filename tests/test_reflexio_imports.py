"""Проверка импортов пакета reflexio (интеграция Golos)."""


def test_reflexio_audio_imports():
    """Импорты из reflexio.audio должны работать."""
    from reflexio.audio import AudioRecorder, VADetector, AudioBuffer
    assert AudioRecorder is not None
    assert VADetector is not None
    assert AudioBuffer is not None


def test_reflexio_transcription_import():
    """Импорт WhisperEngine из reflexio.transcription должен работать."""
    from reflexio.transcription import WhisperEngine
    assert WhisperEngine is not None


def test_reflexio_main_app():
    """src.reflexio.main должен экспортировать app."""
    from src.reflexio.main import app
    assert app is not None
