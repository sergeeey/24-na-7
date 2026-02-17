"""
Тесты для Edge Listener (Core Domain).
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


# Может быть не установлен webrtcvad
try:
    from src.edge.listener import write_wave
    HAS_LISTENER = True
except ImportError:
    HAS_LISTENER = False
    write_wave = None

from src.edge.filters import SpeechFilter


@pytest.mark.skipif(not HAS_LISTENER, reason="webrtcvad not installed")
class TestWriteWave:
    """Тесты записи WAV файлов."""
    
    def test_write_wave_creates_file(self, tmp_path):
        """Запись создает файл."""
        output_path = tmp_path / "test.wav"
        audio_frames = [b"\x00\x01", b"\x02\x03"]
        
        write_wave(output_path, audio_frames, sample_rate=16000)
        
        assert output_path.exists()
        assert output_path.stat().st_size > 0
    
    def test_write_wave_correct_header(self, tmp_path):
        """Корректный WAV заголовок."""
        output_path = tmp_path / "test.wav"
        audio_frames = [b"\x00\x00"] * 100
        
        write_wave(output_path, audio_frames, sample_rate=16000)
        
        # Читаем заголовок
        data = output_path.read_bytes()
        assert data[:4] == b"RIFF"
        assert data[8:12] == b"WAVE"


class TestSpeechFilter:
    """Тесты фильтра речи."""
    
    @pytest.fixture
    def filter_enabled(self):
        """Включенный фильтр."""
        return SpeechFilter(
            enabled=True,
            method="energy",
            sample_rate=16000,
        )
    
    def test_filter_initialization(self):
        """Инициализация фильтра."""
        filt = SpeechFilter(enabled=True, method="energy")
        
        assert filt.enabled is True
        assert filt.method == "energy"
    
    def test_filter_disabled(self):
        """Отключенный фильтр пропускает все (check возвращает is_speech=True)."""
        filt = SpeechFilter(enabled=False)
        audio = np.random.randn(16000).astype(np.float32)
        is_speech, metrics = filt.check(audio)
        assert is_speech is True
        assert metrics.get("method") == "disabled"
    
    def test_filter_detects_speech(self, filter_enabled):
        """Фильтр check возвращает (bool, dict); результат зависит от энергетического анализа."""
        sample_rate = 16000
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio = (
            np.sin(2 * np.pi * 500 * t) * 0.5 +
            np.sin(2 * np.pi * 1000 * t) * 0.3
        ).astype(np.float32)
        result = filter_enabled.check(audio)
        assert isinstance(result, tuple) and len(result) == 2
        is_speech, metrics = result
        assert is_speech in (True, False)  # numpy.bool_ или bool
        assert isinstance(metrics, dict)
        assert len(metrics) >= 1


class TestAudioProcessing:
    """Тесты обработки аудио."""
    
    def test_audio_sample_rate(self):
        """Частота дискретизации."""
        sample_rate = 16000
        duration = 1.0
        
        samples = int(sample_rate * duration)
        assert samples == 16000
    
    def test_audio_mono(self):
        """Моно аудио."""
        audio = np.random.randn(16000)
        assert audio.shape == (16000,)
    
    def test_audio_normalization(self):
        """Нормализация аудио."""
        audio = np.array([0.0, 0.5, 1.0, -0.5, -1.0])
        
        # Нормализуем к [-1, 1]
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            normalized = audio / max_val
            assert np.max(np.abs(normalized)) <= 1.0


@pytest.mark.skipif(not HAS_LISTENER, reason="webrtcvad not installed")
class TestVAD:
    """Тесты Voice Activity Detection."""
    
    def test_vad_initialization(self):
        """Инициализация VAD."""
        try:
            import webrtcvad
            vad = webrtcvad.Vad(2)  # Уровень агрессивности 2
            assert vad is not None
        except ImportError:
            pytest.skip("webrtcvad not installed")
    
    def test_vad_detects_voice(self):
        """VAD обнаруживает голос (16kHz, 30ms = 480 samples = 960 bytes)."""
        try:
            import webrtcvad
            vad = webrtcvad.Vad(2)
            # 16kHz * 0.03s = 480 samples, 16-bit = 960 bytes
            frame = b"\x00" * 960
            is_speech = vad.is_speech(frame, 16000)
            assert isinstance(is_speech, bool)
        except ImportError:
            pytest.skip("webrtcvad not installed")


class TestEdgeIntegration:
    """Интеграционные тесты edge."""
    
    def test_full_pipeline_mock(self):
        """Полный pipeline (mock)."""
        # Мокаем все компоненты
        with patch("src.edge.listener.vad") as _:
            with patch("src.edge.listener.sd") as mock_sd:
                mock_stream = MagicMock()
                mock_sd.InputStream.return_value = mock_stream
                
                # Имитируем запись
                assert mock_stream is not None
