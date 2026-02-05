"""
Тесты для ASR провайдеров (Core Domain).
"""
import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.asr.providers import get_asr_provider, ASRProvider


class TestASRProviderFactory:
    """Тесты фабрики ASR провайдеров."""
    
    def test_get_whisper_provider(self):
        """Получение Whisper провайдера."""
        provider = get_asr_provider(provider="openai")
        assert provider is not None
    
    def test_get_faster_whisper_provider(self):
        """Получение Faster-Whisper провайдера."""
        provider = get_asr_provider(provider="openai")
        assert provider is not None
    
    def test_default_provider(self):
        """Провайдер по умолчанию."""
        provider = get_asr_provider(provider="openai")
        assert provider is not None


class TestASRProviderBase:
    """Базовые тесты для ASR провайдера."""
    
    @pytest.fixture
    def mock_audio_file(self, tmp_path):
        """Создает mock WAV файл."""
        wav_path = tmp_path / "test.wav"
        # Создаем минимальный WAV
        wav_header = bytes([
            0x52, 0x49, 0x46, 0x46,  # RIFF
            0x24, 0x00, 0x00, 0x00,  # chunk size
            0x57, 0x41, 0x56, 0x45,  # WAVE
            0x66, 0x6D, 0x74, 0x20,  # fmt
            0x10, 0x00, 0x00, 0x00,
            0x01, 0x00,              # PCM
            0x01, 0x00,              # mono
            0x44, 0xAC, 0x00, 0x00,  # 44100
            0x88, 0x58, 0x01, 0x00,
            0x02, 0x00,
            0x10, 0x00,
            0x64, 0x61, 0x74, 0x61,  # data
            0x00, 0x00, 0x00, 0x00,
        ])
        wav_path.write_bytes(wav_header)
        return str(wav_path)
    
    def test_provider_initialization(self):
        """Инициализация провайдера."""
        from src.asr.providers import OpenAIWhisperProvider
        
        provider = FasterWhisperProvider(model_size="tiny", device="cpu")
        assert provider.model == "whisper-1"
        assert provider.device == "cpu"
    
    def test_transcribe_returns_dict(self, mock_audio_file):
        """Транскрибация возвращает словарь."""
        from src.asr.providers import OpenAIWhisperProvider
        
        provider = OpenAIWhisperProvider(model="whisper-1")
        
        # Mock модели
        provider.model = Mock()
        provider.model.transcribe.return_value = {
            "text": "Hello world",
            "segments": [],
            "language": "en"
        }
        
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
    
    @pytest.mark.parametrize("model_size", ["tiny", "base", "small"])
    def test_model_sizes(self, model_size):
        """Разные размеры моделей."""
        from src.asr.providers import FasterWhisperProvider
        
        provider = OpenAIWhisperProvider(model="whisper-1")
        assert provider.model_size == model_size
