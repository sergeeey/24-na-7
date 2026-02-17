"""Проверка импортов пакета reflexio (интеграция Golos)."""
import pytest


@pytest.mark.skipif(
    not __import__("importlib.util").util.find_spec("reflexio"),
    reason="reflexio package not installed or not on path",
)
def test_reflexio_audio_imports():
    """Импорты из reflexio.audio должны работать."""
    from reflexio.audio import AudioRecorder, VADetector, AudioBuffer
    assert AudioRecorder is not None
    assert VADetector is not None
    assert AudioBuffer is not None


@pytest.mark.skipif(
    not __import__("importlib.util").util.find_spec("reflexio"),
    reason="reflexio package not installed or not on path",
)
def test_reflexio_transcription_import():
    """Импорт WhisperEngine из reflexio.transcription должен работать."""
    from reflexio.transcription import WhisperEngine
    assert WhisperEngine is not None


def test_reflexio_main_app():
    """src.reflexio.main должен экспортировать app."""
    pytest.importorskip("reflexio", reason="reflexio package not installed")
    from src.reflexio.main import app
    assert app is not None
