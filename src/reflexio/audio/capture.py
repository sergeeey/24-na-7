"""
Захват аудио с микрофона с использованием VAD.
Интеграция из Golos: запись речи с детекцией активности.
"""
import wave
import time
from pathlib import Path
from typing import Optional, Callable, List

import numpy as np
import sounddevice as sd

from reflexio.audio.vad import VADetector
from reflexio.audio.buffer import AudioBuffer


class AudioRecorder:
    """
    Записывает аудио с микрофона с сегментацией по VAD.
    Сохраняет сегменты в WAV-файлы при накоплении тишины.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        silence_limit_sec: float = 2.0,
        vad_aggressiveness: int = 2,
        output_dir: Optional[Path] = None,
    ) -> None:
        """
        Args:
            sample_rate: Частота дискретизации.
            frame_duration_ms: Длительность кадра в мс (10, 20, 30).
            silence_limit_sec: Секунд тишины для завершения сегмента.
            vad_aggressiveness: 0-3 для VAD.
            output_dir: Директория для сохранения WAV (по умолчанию текущая).
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.silence_limit_sec = silence_limit_sec
        self.output_dir = Path(output_dir) if output_dir else Path(".")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._vad = VADetector(aggressiveness=vad_aggressiveness, sample_rate=sample_rate)
        self._buffer = AudioBuffer()
        self._silence_elapsed = 0.0
        self._frame_sec = frame_duration_ms / 1000.0
        self._block_size = int(sample_rate * self._frame_sec)
        self._running = False

    def _write_wav(self, path: Path, frames: List[bytes]) -> None:
        """Записывает кадры в WAV-файл."""
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(frames))

    def _on_segment_complete(self, frames: List[bytes]) -> Optional[Path]:
        """
        Вызывается при завершении сегмента. Сохраняет WAV и возвращает путь.
        Переопределяется при необходимости.
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        path = self.output_dir / f"{timestamp}.wav"
        self._write_wav(path, frames)
        return path

    def start(self, segment_callback: Optional[Callable[[Path], None]] = None) -> None:
        """
        Запускает запись в фоне. Сегменты сохраняются на диск;
        если передан segment_callback — вызывается с путём к файлу.
        """
        self._running = True
        segment_cb = segment_callback

        def callback(indata: np.ndarray, frames: int, time_info, status) -> None:
            if not self._running:
                return
            pcm = (indata * 32768).astype(np.int16).tobytes()
            is_speech = self._vad.is_speech(pcm, self.sample_rate)

            if is_speech:
                self._buffer.append(pcm)
                self._silence_elapsed = 0.0
            elif not self._buffer.is_empty():
                self._silence_elapsed += self._frame_sec
                self._buffer.append(pcm)
                if self._silence_elapsed >= self.silence_limit_sec:
                    frames_data = list(self._buffer._frames)
                    self._buffer.clear()
                    self._silence_elapsed = 0.0
                    path = self._on_segment_complete(frames_data)
                    if path and segment_cb:
                        segment_cb(path)

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self._block_size,
            dtype="float32",
            channels=1,
            callback=callback,
        ):
            while self._running:
                time.sleep(0.1)

    def stop(self) -> None:
        """Останавливает запись."""
        self._running = False

    def record_segment(self, duration_sec: float, output_path: Optional[Path] = None) -> Path:
        """
        Записывает один сегмент фиксированной длительности (без VAD).

        Args:
            duration_sec: Длительность в секундах.
            output_path: Куда сохранить WAV. По умолчанию — в output_dir с таймстампом.

        Returns:
            Путь к сохранённому файлу.
        """
        num_frames = int(self.sample_rate * duration_sec)
        block = self._block_size
        frames: List[bytes] = []
        recorded = 0

        def callback(indata: np.ndarray, f: int, time_info, status) -> None:
            nonlocal recorded
            if recorded >= num_frames:
                return
            pcm = (indata * 32768).astype(np.int16).tobytes()
            frames.append(pcm)
            recorded += block

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=block,
            dtype="float32",
            channels=1,
            callback=callback,
        ):
            while recorded < num_frames:
                time.sleep(0.05)

        path = output_path or (self.output_dir / f"{time.strftime('%Y%m%d_%H%M%S')}.wav")
        self._write_wav(path, frames)
        return path
