"""
Тесты для доведения покрытия asr/providers до 80%.
Без загрузки ctranslate2/faster_whisper — только моки.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_get_asr_provider_openai_with_mock():
    """get_asr_provider('openai') с замоканным openai клиентом."""
    from src.asr.providers import get_asr_provider

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-fake"}, clear=False):
        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            provider = get_asr_provider("openai")
    assert provider is not None
    assert hasattr(provider, "transcribe")


def test_get_asr_provider_openai_no_key_raises():
    """get_asr_provider('openai') без API ключа бросает ValueError."""
    from src.asr.providers import get_asr_provider

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            get_asr_provider("openai")


def test_get_asr_provider_unknown_raises():
    """get_asr_provider с неизвестным провайдером бросает ValueError."""
    from src.asr.providers import get_asr_provider

    with pytest.raises(ValueError, match="Unknown provider"):
        get_asr_provider("unknown_xyz_provider")


def test_get_asr_provider_local_returns_provider():
    """get_asr_provider('local') возвращает LocalProvider (обёртка над transcribe_audio)."""
    from src.asr.providers import get_asr_provider

    with patch("src.asr.transcribe.transcribe_audio") as mock_ta:
        mock_ta.return_value = {"text": "hello", "segments": [], "language": "en"}
        provider = get_asr_provider("local")
        assert provider is not None
        assert hasattr(provider, "transcribe")
        assert hasattr(provider, "get_latency")
        result = provider.transcribe(Path("fake.wav"))
    assert result["text"] == "hello"
    assert mock_ta.called


def test_get_asr_provider_whisperx_mock():
    """get_asr_provider('whisperx') с замоканным WhisperXProvider (без загрузки модели)."""
    from src.asr.providers import get_asr_provider

    with patch("src.asr.providers.WhisperXProvider", MagicMock(return_value=MagicMock())):
        provider = get_asr_provider("whisperx")
    assert provider is not None


def test_get_asr_provider_distil_mock():
    """get_asr_provider('distil-whisper') с замоканным DistilWhisperProvider."""
    from src.asr.providers import get_asr_provider

    with patch("src.asr.providers.DistilWhisperProvider", MagicMock(return_value=MagicMock())):
        provider = get_asr_provider("distil-whisper")
    assert provider is not None


def test_get_asr_provider_parakeet_mock():
    """get_asr_provider('parakeet') с замоканным ParaKeetProvider."""
    from src.asr.providers import get_asr_provider

    with patch("src.asr.providers.ParaKeetProvider", MagicMock(return_value=MagicMock())):
        provider = get_asr_provider("parakeet")
    assert provider is not None


def test_openai_provider_get_latency():
    """OpenAIWhisperProvider.get_latency возвращает 0 при пустой истории."""
    from src.asr.providers import OpenAIWhisperProvider

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-x"}, clear=False):
        with patch("openai.OpenAI") as m:
            m.return_value = MagicMock()
            p = OpenAIWhisperProvider()
    assert p.get_latency() == 0.0
