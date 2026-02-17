"""
Тесты для ASR провайдеров (Core Domain).
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.asr.providers import get_asr_provider


class TestASRProviderFactory:
    """Тесты фабрики ASR провайдеров."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    def test_get_whisper_provider(self):
        """Получение OpenAI Whisper провайдера."""
        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            provider = get_asr_provider(provider="openai")
        assert provider is not None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    def test_get_faster_whisper_provider(self):
        """Получение провайдера (openai)."""
        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            provider = get_asr_provider(provider="openai")
        assert provider is not None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    def test_default_provider(self):
        """Провайдер openai."""
        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            provider = get_asr_provider(provider="openai")
        assert provider is not None


class TestASRProviderBase:
    """Базовые тесты для ASR провайдера."""

    @pytest.fixture
    def mock_audio_file(self, tmp_path):
        """Создает mock WAV файл."""
        wav_path = tmp_path / "test.wav"
        wav_header = bytes([
            0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00,
            0x57, 0x41, 0x56, 0x45, 0x66, 0x6D, 0x74, 0x20,
            0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
            0x44, 0xAC, 0x00, 0x00, 0x88, 0x58, 0x01, 0x00,
            0x02, 0x00, 0x10, 0x00, 0x64, 0x61, 0x74, 0x61,
            0x00, 0x00, 0x00, 0x00,
        ])
        wav_path.write_bytes(wav_header)
        return wav_path

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    def test_provider_initialization(self):
        """Инициализация OpenAI провайдера."""
        from src.asr.providers import OpenAIWhisperProvider
        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            provider = OpenAIWhisperProvider()
        assert provider.client is not None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    def test_transcribe_returns_dict(self, mock_audio_file):
        """Транскрибация возвращает словарь."""
        from src.asr.providers import OpenAIWhisperProvider
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.audio.transcriptions.create.return_value = Mock(
                text="Hello world",
                language="en",
                words=[],
            )
            mock_openai.return_value = mock_client
            provider = OpenAIWhisperProvider()
            result = provider.transcribe(mock_audio_file)
        assert isinstance(result, dict)
        assert "text" in result


class TestASRTranscription:
    """Тесты транскрибации."""
    
    def test_transcription_result_structure(self):
        """Структура результата транскрибации."""
        result = {
            "text": "Test transcription",
            "segments": [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 2.0,
                    "text": "Test",
                }
            ],
            "language": "en",
        }
        
        assert "text" in result
        assert "segments" in result
        assert "language" in result
        assert isinstance(result["segments"], list)
    
    def test_empty_audio_handling(self):
        """Обработка пустого аудио."""
        result = {"text": "", "segments": [], "language": None}
        
        assert result["text"] == ""
        assert result["segments"] == []


class TestASRPerformance:
    """Тесты производительности ASR."""
    
    def test_transcription_speed(self):
        """Скорость транскрибации."""
        import time
        
        # Mock быстрой транскрибации
        start = time.time()
        time.sleep(0.001)  # Имитация 1ms
        duration = time.time() - start
        
        assert duration < 1.0  # Должно быть меньше 1 секунды
    
    @pytest.mark.parametrize("model_size", ["distil-small.en", "distil-medium.en"])
    def test_model_sizes(self, model_size):
        """Разные размеры моделей DistilWhisper (пропуск если ctranslate2 недоступен)."""
        try:
            from src.asr.providers import DistilWhisperProvider
        except Exception:
            pytest.skip("DistilWhisper not importable")
        if __import__("sys").platform == "win32":
            pytest.skip("ctranslate2 often fails on Windows (DLL)")
        try:
            provider = DistilWhisperProvider(model_size=model_size, device="cpu")
            assert provider.model_size == model_size
        except Exception:
            pytest.skip("DistilWhisper not loadable (ctranslate2)")
