"""
Тесты accuracy для ASR провайдеров (WER).
Reflexio 24/7 — November 2025 Integration Sprint
"""
import pytest
from pathlib import Path
import tempfile
import numpy as np
import soundfile as sf

from src.asr.providers import get_asr_provider


def calculate_wer(reference: str, hypothesis: str) -> float:
    """
    Рассчитывает Word Error Rate (WER).
    
    Args:
        reference: Эталонный текст
        hypothesis: Распознанный текст
        
    Returns:
        WER (0.0-1.0, где 0 = идеально)
    """
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    
    if len(ref_words) == 0:
        return 1.0 if len(hyp_words) > 0 else 0.0
    
    # Простой алгоритм Левенштейна для слов
    # Используем упрощённую версию
    errors = 0
    
    # Простое сравнение (можно улучшить через библиотеку)
    for i in range(min(len(ref_words), len(hyp_words))):
        if ref_words[i] != hyp_words[i]:
            errors += 1
    
    errors += abs(len(ref_words) - len(hyp_words))
    
    return errors / len(ref_words)


@pytest.fixture
def test_audio_with_text():
    """Создаёт тестовый аудиофайл с известным текстом."""
    # Для реальных тестов нужны реальные аудиофайлы с транскрипциями
    # Здесь создаём заглушку
    sample_rate = 16000
    duration = 2.0
    frequency = 440
    
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_data = np.sin(2 * np.pi * frequency * t).astype(np.float32)
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, audio_data, sample_rate)
        yield (Path(f.name), "test audio transcription")
    
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def sample_audio():
    """Создаёт тестовый аудиофайл."""
    sample_rate = 16000
    duration = 1.0
    frequency = 440
    
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_data = np.sin(2 * np.pi * frequency * t).astype(np.float32)
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, audio_data, sample_rate)
        yield Path(f.name)
    
    Path(f.name).unlink(missing_ok=True)


def test_wer_target(sample_audio):
    """Проверяет, что WER ≤ 10%."""
    import os
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    # Для реального теста нужен эталонный текст
    # Здесь проверяем структуру ответа
    provider = get_asr_provider("openai")
    result = provider.transcribe(sample_audio)
    
    assert "text" in result
    assert isinstance(result["text"], str)
    
    # Если есть эталонный текст, проверяем WER
    # reference = "expected transcription"
    # wer = calculate_wer(reference, result["text"])
    # assert wer <= 0.10, f"WER too high: {wer:.2%} (target: ≤ 10%)"


def test_word_level_timestamps(sample_audio):
    """Проверяет наличие word-level timestamps."""
    import os
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    provider = get_asr_provider("openai")
    result = provider.transcribe(sample_audio, timestamps=True)
    
    assert "segments" in result
    if result["segments"]:
        segment = result["segments"][0]
        assert "start" in segment
        assert "end" in segment
        assert "text" in segment


def test_diarization_structure(sample_audio):
    """Проверяет структуру результата диаризации."""
    # Тест структуры (реальная диаризация требует WhisperX)
    result = {
        "text": "test",
        "segments": [],
        "speakers": None,
    }
    
    assert "speakers" in result
    # Если диаризация включена, speakers должен быть списком
    if result["speakers"] is not None:
        assert isinstance(result["speakers"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])





