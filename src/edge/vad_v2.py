"""
WebRTC VAD v2 с adaptive gain control для улучшенного детектирования речи.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import webrtcvad
import numpy as np
from typing import Tuple, Optional, List
from collections import deque

from src.utils.logging import get_logger

logger = get_logger("edge.vad_v2")


class AdaptiveGainControl:
    """Адаптивная регулировка усиления для улучшения качества VAD."""
    
    def __init__(
        self,
        target_level: float = 0.3,
        max_gain: float = 10.0,
        min_gain: float = 0.1,
        smoothing_factor: float = 0.1,
    ):
        """
        Args:
            target_level: Целевой уровень сигнала (0.0-1.0)
            max_gain: Максимальное усиление
            min_gain: Минимальное усиление
            smoothing_factor: Коэффициент сглаживания (0.0-1.0)
        """
        self.target_level = target_level
        self.max_gain = max_gain
        self.min_gain = min_gain
        self.smoothing_factor = smoothing_factor
        self.current_gain = 1.0
        self._level_history = deque(maxlen=10)  # История уровней для сглаживания
    
    def apply(self, audio: np.ndarray) -> np.ndarray:
        """
        Применяет адаптивное усиление к аудио.
        
        Args:
            audio: Аудио сигнал (float32, -1.0 до 1.0)
            
        Returns:
            Обработанный аудио сигнал
        """
        # Вычисляем текущий уровень сигнала (RMS)
        current_level = np.sqrt(np.mean(audio ** 2))
        
        if current_level > 0:
            # Добавляем в историю
            self._level_history.append(current_level)
            
            # Вычисляем средний уровень из истории
            avg_level = np.mean(list(self._level_history))
            
            # Вычисляем необходимое усиление
            if avg_level > 0:
                desired_gain = self.target_level / avg_level
                desired_gain = np.clip(desired_gain, self.min_gain, self.max_gain)
                
                # Сглаживаем изменение усиления
                self.current_gain = (
                    self.smoothing_factor * desired_gain +
                    (1 - self.smoothing_factor) * self.current_gain
                )
        
        # Применяем усиление
        amplified = audio * self.current_gain
        
        # Предотвращаем клиппинг
        amplified = np.clip(amplified, -1.0, 1.0)
        
        return amplified
    
    def reset(self):
        """Сбрасывает состояние AGC."""
        self.current_gain = 1.0
        self._level_history.clear()


class WebRTCVADv2:
    """
    Улучшенный WebRTC VAD с adaptive gain control и улучшенной обработкой.
    """
    
    def __init__(
        self,
        aggressiveness: int = 2,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        enable_agc: bool = True,
        enable_smoothing: bool = True,
    ):
        """
        Args:
            aggressiveness: Уровень агрессивности VAD (0-3)
            sample_rate: Частота дискретизации (8000, 16000, 32000, 48000)
            frame_duration_ms: Длительность кадра в мс (10, 20, 30)
            enable_agc: Включить adaptive gain control
            enable_smoothing: Включить сглаживание результатов
        """
        if sample_rate not in [8000, 16000, 32000, 48000]:
            raise ValueError(f"Unsupported sample rate: {sample_rate}")
        if frame_duration_ms not in [10, 20, 30]:
            raise ValueError(f"Unsupported frame duration: {frame_duration_ms}")
        
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        
        self.enable_agc = enable_agc
        self.enable_smoothing = enable_smoothing
        
        if enable_agc:
            self.agc = AdaptiveGainControl()
        else:
            self.agc = None
        
        # История для сглаживания
        if enable_smoothing:
            self._speech_history = deque(maxlen=5)  # История последних 5 кадров
        else:
            self._speech_history = None
        
        logger.info(
            "vad_v2_initialized",
            aggressiveness=aggressiveness,
            sample_rate=sample_rate,
            frame_duration_ms=frame_duration_ms,
            agc_enabled=enable_agc,
            smoothing_enabled=enable_smoothing,
        )
    
    def is_speech(self, audio: np.ndarray) -> bool:
        """
        Определяет, содержит ли аудио речь.
        
        Args:
            audio: Аудио сигнал (float32, -1.0 до 1.0) или (int16)
            
        Returns:
            True если обнаружена речь
        """
        # Конвертируем в int16 если нужно
        if audio.dtype == np.float32:
            # Нормализуем и конвертируем в int16
            audio_int16 = (audio * 32768).astype(np.int16)
        elif audio.dtype == np.int16:
            audio_int16 = audio
        else:
            raise ValueError(f"Unsupported audio dtype: {audio.dtype}")
        
        # Применяем AGC если включён
        if self.agc:
            audio_float = audio_int16.astype(np.float32) / 32768.0
            audio_float = self.agc.apply(audio_float)
            audio_int16 = (audio_float * 32768).astype(np.int16)
        
        # Конвертируем в bytes для VAD
        audio_bytes = audio_int16.tobytes()
        
        # Проверяем длину (должна соответствовать frame_size)
        expected_bytes = self.frame_size * 2  # int16 = 2 bytes
        if len(audio_bytes) != expected_bytes:
            # Обрезаем или дополняем нулями
            if len(audio_bytes) < expected_bytes:
                audio_bytes = audio_bytes + b"\x00" * (expected_bytes - len(audio_bytes))
            else:
                audio_bytes = audio_bytes[:expected_bytes]
        
        # Проверяем через VAD
        is_speech = self.vad.is_speech(audio_bytes, self.sample_rate)
        
        # Сглаживание результатов
        if self.enable_smoothing and self._speech_history is not None:
            self._speech_history.append(is_speech)
            
            # Если большинство последних кадров — речь, считаем что речь
            if len(self._speech_history) >= 3:
                speech_count = sum(self._speech_history)
                is_speech = speech_count >= 2  # 2 из 3 или больше
        
        return is_speech
    
    def process_stream(
        self,
        audio_stream: List[np.ndarray],
        min_speech_frames: int = 3,
    ) -> Tuple[bool, dict]:
        """
        Обрабатывает поток аудио и определяет наличие речи.
        
        Args:
            audio_stream: Список аудио кадров
            min_speech_frames: Минимальное количество кадров с речью для положительного результата
            
        Returns:
            Tuple[bool, dict]: (есть_ли_речь, метрики)
        """
        speech_frames = 0
        total_frames = len(audio_stream)
        
        for frame in audio_stream:
            if self.is_speech(frame):
                speech_frames += 1
        
        speech_ratio = speech_frames / total_frames if total_frames > 0 else 0.0
        has_speech = speech_frames >= min_speech_frames
        
        metrics = {
            "speech_frames": speech_frames,
            "total_frames": total_frames,
            "speech_ratio": speech_ratio,
            "agc_gain": self.agc.current_gain if self.agc else 1.0,
        }
        
        return has_speech, metrics
    
    def reset(self):
        """Сбрасывает состояние VAD."""
        if self.agc:
            self.agc.reset()
        if self._speech_history:
            self._speech_history.clear()
        logger.debug("vad_v2_reset")





