"""Тесты латентности транскрипции."""
import pytest
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.asr.transcribe import transcribe_audio


@pytest.mark.performance
def test_transcription_latency():
    """Проверка латентности транскрипции."""
    # Создаём тестовый аудио файл
    test_audio = Path("/tmp/test_audio.wav")
    test_audio.write_bytes(b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00')
    
    with patch("src.asr.transcribe.get_asr_provider") as mock_provider:
        mock_provider_instance = MagicMock()
        mock_provider_instance.transcribe.return_value = {
            "text": "Тестовая транскрипция",
            "language": "ru",
            "segments": []
        }
        mock_provider.return_value = mock_provider_instance
        
        start_time = time.time()
        result = transcribe_audio(test_audio)
        latency = (time.time() - start_time) * 1000
        
        # Проверяем что транскрипция выполнена
        assert "text" in result
        
        # SLA: транскрипция должна выполняться быстро (для моков < 100ms)
        assert latency < 100, f"Latency {latency}ms превышает ожидаемое значение"
        
        print(f"Transcription latency: {latency:.2f}ms")
    
    # Очистка
    test_audio.unlink(missing_ok=True)
