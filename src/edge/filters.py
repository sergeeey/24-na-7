"""Фильтры для распознавания речи и отсечения музыки/шума."""
import numpy as np
from typing import Optional, Tuple
from pathlib import Path

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("edge.filters")

# Попытка импорта librosa (опционально)
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logger.warning("librosa_not_available", message="Energy filter will use numpy-only fallback")


def is_speech_energy_filter(
    audio: np.ndarray,
    sample_rate: int = 16000,
    speech_band_low: int = 300,
    speech_band_high: int = 3400,
    energy_threshold: float = 0.4,
    high_freq_threshold: float = 0.3,
) -> Tuple[bool, dict]:
    """
    Определяет, является ли аудио речью на основе энергетического анализа спектра.
    
    Принцип: человеческая речь имеет основную энергию в диапазоне 300-3400 Гц.
    Музыка обычно имеет широкий спектр (20-20000 Гц) с высокой энергией выше 4 кГц.
    
    Args:
        audio: Аудио сигнал (1D numpy array)
        sample_rate: Частота дискретизации
        speech_band_low: Нижняя граница речевого диапазона (Гц)
        speech_band_high: Верхняя граница речевого диапазона (Гц)
        energy_threshold: Порог доли энергии в речевом диапазоне (0-1)
        high_freq_threshold: Порог доли энергии выше 4 кГц (для фильтрации музыки)
        
    Returns:
        Tuple[bool, dict]: (является_ли_речью, метрики_анализа)
    """
    if len(audio) == 0:
        return False, {"reason": "empty_audio"}
    
    # Нормализуем аудио
    audio = audio.astype(np.float32)
    if np.max(np.abs(audio)) > 0:
        audio = audio / (np.max(np.abs(audio)) + 1e-6)
    
    if LIBROSA_AVAILABLE:
        # Используем librosa для спектрального анализа
        try:
            # Короткое преобразование Фурье
            S = np.abs(librosa.stft(audio, n_fft=2048, hop_length=512))
            
            # Частоты для каждого бина
            freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
            
            # Энергия в речевом диапазоне (300-3400 Гц)
            speech_band_mask = (freqs >= speech_band_low) & (freqs <= speech_band_high)
            speech_energy = np.sum(S[speech_band_mask, :])
            
            # Энергия в высоких частотах (> 4 кГц) - часто музыка
            high_freq_mask = freqs > 4000
            high_freq_energy = np.sum(S[high_freq_mask, :])
            
            # Общая энергия
            total_energy = np.sum(S)
            
            if total_energy < 1e-6:
                return False, {"reason": "no_energy", "total_energy": 0.0}
            
            # Доли энергии
            speech_ratio = speech_energy / total_energy
            high_freq_ratio = high_freq_energy / total_energy
            
            # Критерии речи:
            # 1. Достаточно энергии в речевом диапазоне
            # 2. Не слишком много энергии в высоких частотах (музыка)
            is_speech = (
                speech_ratio >= energy_threshold and
                high_freq_ratio <= high_freq_threshold
            )
            
            metrics = {
                "speech_ratio": float(speech_ratio),
                "high_freq_ratio": float(high_freq_ratio),
                "total_energy": float(total_energy),
                "is_speech": is_speech,
                "reason": "energy_filter" if is_speech else f"speech_ratio={speech_ratio:.2f}, high_freq={high_freq_ratio:.2f}",
            }
            
            return is_speech, metrics
            
        except Exception as e:
            logger.warning("librosa_analysis_failed", error=str(e))
            # Fallback на numpy-only метод
            return _numpy_energy_filter(audio, sample_rate, speech_band_low, speech_band_high, energy_threshold)
    else:
        # Fallback: простой numpy-only метод
        return _numpy_energy_filter(audio, sample_rate, speech_band_low, speech_band_high, energy_threshold)


def _numpy_energy_filter(
    audio: np.ndarray,
    sample_rate: int,
    speech_band_low: int,
    speech_band_high: int,
    energy_threshold: float,
) -> Tuple[bool, dict]:
    """
    Упрощённый энергетический фильтр без librosa (fallback).
    
    Использует только FFT через numpy.
    """
    try:
        # FFT
        fft = np.fft.rfft(audio)
        freqs = np.fft.rfftfreq(len(audio), 1.0 / sample_rate)
        magnitude = np.abs(fft)
        
        # Энергия в речевом диапазоне
        speech_mask = (freqs >= speech_band_low) & (freqs <= speech_band_high)
        speech_energy = np.sum(magnitude[speech_mask] ** 2)
        
        # Энергия в высоких частотах
        high_freq_mask = freqs > 4000
        high_freq_energy = np.sum(magnitude[high_freq_mask] ** 2)
        
        # Общая энергия
        total_energy = np.sum(magnitude ** 2)
        
        if total_energy < 1e-6:
            return False, {"reason": "no_energy", "total_energy": 0.0}
        
        speech_ratio = speech_energy / total_energy
        high_freq_ratio = high_freq_energy / total_energy
        
        # Упрощённый критерий
        is_speech = (
            speech_ratio >= energy_threshold and
            high_freq_ratio <= 0.3
        )
        
        return is_speech, {
            "speech_ratio": float(speech_ratio),
            "high_freq_ratio": float(high_freq_ratio),
            "total_energy": float(total_energy),
            "is_speech": is_speech,
            "reason": "numpy_energy_filter",
        }
        
    except Exception as e:
        logger.error("numpy_filter_failed", error=str(e))
        return False, {"reason": f"filter_error: {str(e)}"}


def is_speech(
    audio: np.ndarray,
    sample_rate: int = 16000,
    method: str = "energy",
    **kwargs,
) -> Tuple[bool, dict]:
    """
    Универсальная функция проверки, является ли аудио речью.
    
    Args:
        audio: Аудио сигнал
        sample_rate: Частота дискретизации
        method: Метод фильтрации ("energy", "none")
        **kwargs: Дополнительные параметры для фильтров
        
    Returns:
        Tuple[bool, dict]: (является_ли_речью, метрики)
    """
    if method == "none" or method is None:
        return True, {"method": "none", "is_speech": True}
    
    if method == "energy":
        return is_speech_energy_filter(audio, sample_rate, **kwargs)
    
    logger.warning("unknown_filter_method", method=method)
    return True, {"method": "unknown", "is_speech": True, "fallback": True}


class SpeechFilter:
    """Класс для фильтрации речи с кэшированием настроек."""
    
    def __init__(
        self,
        enabled: bool = True,
        method: str = "energy",
        sample_rate: int = 16000,
        **filter_kwargs,
    ):
        """
        Инициализация фильтра.
        
        Args:
            enabled: Включён ли фильтр
            method: Метод фильтрации
            sample_rate: Частота дискретизации
            **filter_kwargs: Параметры фильтра
        """
        self.enabled = enabled
        self.method = method if enabled else "none"
        self.sample_rate = sample_rate
        self.filter_kwargs = filter_kwargs
        
        logger.info(
            "speech_filter_initialized",
            enabled=enabled,
            method=self.method,
            sample_rate=sample_rate,
        )
    
    def check(self, audio: np.ndarray) -> Tuple[bool, dict]:
        """
        Проверяет, является ли аудио речью.
        
        Args:
            audio: Аудио сигнал
            
        Returns:
            Tuple[bool, dict]: (является_ли_речью, метрики)
        """
        if not self.enabled:
            return True, {"method": "disabled", "is_speech": True}
        
        return is_speech(
            audio,
            sample_rate=self.sample_rate,
            method=self.method,
            **self.filter_kwargs,
        )
    
    def filter_segment(self, audio: np.ndarray, segment_info: Optional[dict] = None) -> Tuple[bool, dict]:
        """
        Фильтрует сегмент аудио.
        
        Args:
            audio: Аудио сигнал
            segment_info: Дополнительная информация о сегменте
            
        Returns:
            Tuple[bool, dict]: (пропустить_ли_сегмент, метрики)
        """
        is_valid, metrics = self.check(audio)
        
        # Инвертируем: если это НЕ речь, нужно пропустить (True = пропустить)
        should_skip = not is_valid
        
        if should_skip:
            logger.debug(
                "segment_filtered",
                reason=metrics.get("reason", "unknown"),
                speech_ratio=metrics.get("speech_ratio"),
                high_freq_ratio=metrics.get("high_freq_ratio"),
            )
        
        return should_skip, metrics













