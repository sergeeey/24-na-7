"""
Тесты latency для ASR провайдеров.
Reflexio 24/7 — November 2025 Integration Sprint
"""
import pytest
import time
from pathlib import Path
import tempfile
import numpy as np
import soundfile as sf

from src.asr.providers import OpenAIWhisperProvider
from src.asr.transcribe import transcribe_audio


@pytest.fixture
def sample_audio():
    """Создаёт тестовый аудиофайл."""
    # Создаём простой синусоидальный сигнал (1 секунда, 16kHz)
    sample_rate = 16000
    duration = 1.0
    frequency = 440  # A4 нота
    
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_data = np.sin(2 * np.pi * frequency * t).astype(np.float32)
    
    # Сохраняем во временный файл
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, audio_data, sample_rate)
        yield Path(f.name)
    
    # Удаляем после теста
    Path(f.name).unlink(missing_ok=True)


def test_openai_latency(sample_audio):
    """Тест latency OpenAI Whisper API."""
    import os
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    provider = OpenAIWhisperProvider()
    
    start_time = time.time()
    result = provider.transcribe(sample_audio, timestamps=True)
    latency = time.time() - start_time
    
    assert latency < 2.0, f"Latency too high: {latency:.2f}s (target: < 2.0s)"
    assert "text" in result
    assert result["text"] is not None


def test_transcribe_audio_latency(sample_audio):
    """Тест latency через transcribe_audio с разными провайдерами."""
    import os
    import sys
    # ctranslate2 может падать на Windows (DLL); не импортируем его здесь
    if sys.platform == "win32":
        pytest.skip("ctranslate2/faster_whisper skipped on Windows (DLL load)")
    providers_to_test = ["local"]
    for provider_name in providers_to_test:
        if provider_name == "openai" and not os.getenv("OPENAI_API_KEY"):
            continue
        start_time = time.time()
        result = transcribe_audio(
            sample_audio,
            provider=provider_name,
            timestamps=True,
        )
        latency = time.time() - start_time
        assert latency < 5.0, f"Latency too high for {provider_name}: {latency:.2f}s"
        assert "text" in result
        assert result["provider"] == provider_name


def test_throughput(sample_audio):
    """Тест throughput (должен быть ≥ 5× реального времени)."""
    import os
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    provider = OpenAIWhisperProvider()
    
    # Измеряем время обработки
    start_time = time.time()
    provider.transcribe(sample_audio)
    processing_time = time.time() - start_time
    
    # Длительность аудио (1 секунда)
    audio_duration = 1.0
    
    # Throughput = audio_duration / processing_time
    throughput = audio_duration / processing_time if processing_time > 0 else 0
    
    assert throughput >= 5.0, f"Throughput too low: {throughput:.2f}x (target: ≥ 5.0x)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])





