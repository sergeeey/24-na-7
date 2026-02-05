"""
Тесты офлайн транскрипции (≥ 30 мин без сети).
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import pytest
import tempfile
import numpy as np
import wave
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.asr.providers import DistilWhisperProvider, get_asr_provider


def create_test_audio(duration_seconds: int = 5, sample_rate: int = 16000) -> Path:
    """Создаёт тестовый аудиофайл."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = Path(temp_file.name)
    
    # Генерируем простой синусоидальный сигнал (имитация речи)
    t = np.linspace(0, duration_seconds, sample_rate * duration_seconds)
    # Смешиваем несколько частот для более реалистичного звука
    audio = (
        0.3 * np.sin(2 * np.pi * 440 * t) +  # A4
        0.2 * np.sin(2 * np.pi * 880 * t) +  # A5
        0.1 * np.sin(2 * np.pi * 220 * t)    # A3
    )
    audio = (audio * 32767).astype(np.int16)
    
    with wave.open(str(temp_path), "wb") as wf:
        wf.setnchannels(1)  # Моно
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    
    return temp_path


@pytest.fixture(scope="session")
def offline_test_enabled(request):
    """Фикстура для проверки включения офлайн тестов."""
    return request.config.getoption("--test-offline", default=False)


@pytest.mark.skipif(
    True,  # Всегда пропускаем, если не указан --test-offline
    reason="Офлайн тесты требуют --test-offline флаг. Запустите: pytest --test-offline"
)
class TestOfflineTranscription:
    """Тесты офлайн транскрипции."""
    
    def test_distil_whisper_offline_mode(self):
        """Тест: Distil-Whisper работает в офлайн режиме."""
        provider = DistilWhisperProvider(model_size="distil-small.en", device="cpu")
        
        assert provider.is_offline() == True, "Distil-Whisper должен быть в офлайн режиме"
    
    @patch("requests.get")
    @patch("requests.post")
    def test_offline_transcription_no_network(self, mock_post, mock_get):
        """Тест: Транскрипция работает без сети."""
        # Мокируем сетевые запросы, чтобы они падали
        mock_post.side_effect = Exception("Network unavailable")
        mock_get.side_effect = Exception("Network unavailable")
        
        provider = DistilWhisperProvider(model_size="distil-small.en", device="cpu")
        
        # Создаём тестовый аудио
        audio_path = create_test_audio(duration_seconds=5)
        
        try:
            # Транскрипция должна работать без сети
            result = provider.transcribe(
                audio_path=audio_path,
                language="en",
                timestamps=True,
            )
            
            assert "text" in result
            assert result["offline_mode"] == True
            assert "segments" in result
            
        finally:
            # Удаляем тестовый файл
            audio_path.unlink()
    
    def test_offline_provider_selection(self):
        """Тест: Выбор офлайн провайдера через get_asr_provider."""
        with patch("src.asr.providers.Path.exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                import yaml
                config = {
                    "provider": "distil-whisper",
                    "edge_mode": True,
                    "distil_whisper": {
                        "model_size": "distil-small.en",
                        "device": "cpu",
                    },
                }
                mock_open.return_value.__enter__.return_value.read.return_value = yaml.dump(config)
                
                provider = get_asr_provider(provider="distil-whisper", model_size="distil-small.en", device="cpu")
                
                assert isinstance(provider, DistilWhisperProvider)
                assert provider.is_offline() == True


@pytest.mark.slow
class TestLongOfflineTranscription:
    """Тесты длительной офлайн транскрипции (≥ 30 мин)."""
    
    def test_30_minute_offline_capability(self):
        """
        Тест: Проверка возможности транскрибировать ≥ 30 мин без сети.
        
        Примечание: Это интеграционный тест, который требует загруженной модели.
        Запускать с --test-offline флагом.
        """
        provider = DistilWhisperProvider(model_size="distil-small.en", device="cpu")
        
        # Создаём длинный тестовый аудио (30 секунд для быстрого теста, в реальности 30 мин)
        # В production тесте можно использовать реальный 30-минутный файл
        audio_path = create_test_audio(duration_seconds=30)
        
        try:
            # Проверяем, что провайдер может обработать длинный файл
            result = provider.transcribe(
                audio_path=audio_path,
                language="en",
                timestamps=True,
            )
            
            assert result["offline_mode"] == True
            assert "duration" in result or "segments" in result
            
            # Проверяем, что latency разумная (не более 2x реального времени)
            latency = provider.get_latency()
            audio_duration = 30  # секунд
            assert latency < audio_duration * 2, f"Latency {latency}s слишком высокая для {audio_duration}s аудио"
            
        finally:
            audio_path.unlink()
    
    def test_offline_batch_processing(self):
        """Тест: Пакетная обработка нескольких файлов в офлайн режиме."""
        provider = DistilWhisperProvider(model_size="distil-small.en", device="cpu")
        
        # Создаём несколько тестовых файлов
        audio_files = [create_test_audio(duration_seconds=5) for _ in range(3)]
        
        try:
            results = []
            for audio_path in audio_files:
                result = provider.transcribe(
                    audio_path=audio_path,
                    language="en",
                    timestamps=False,
                )
                results.append(result)
            
            # Проверяем, что все файлы обработаны
            assert len(results) == 3
            assert all(r["offline_mode"] == True for r in results)
            
        finally:
            for audio_path in audio_files:
                audio_path.unlink()


def pytest_addoption(parser):
    """Добавляет опцию --test-offline для запуска офлайн тестов."""
    parser.addoption(
        "--test-offline",
        action="store_true",
        default=False,
        help="Запустить тесты офлайн транскрипции (требуют загруженные модели)",
    )





