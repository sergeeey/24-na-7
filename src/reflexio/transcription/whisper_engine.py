"""
Движок транскрипции на базе Whisper / faster-whisper.
Интеграция из Golos: единый интерфейс WhisperEngine.
"""
from pathlib import Path
from typing import Optional, Dict, Any


class WhisperEngine:
    """
    Обёртка над ASR для транскрипции аудио.
    Использует конфигурацию 24 na 7 (src.asr).
    """

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        """
        Args:
            model_size: Размер модели (tiny, base, small, medium, large). По умолчанию из настроек.
            device: cpu или cuda. По умолчанию из настроек.
            language: Код языка (ru, en и т.д.). None — автоопределение.
        """
        self._model_size = model_size
        self._device = device
        self._language = language
        self._provider = None

    def _get_provider(self):
        """Ленивая инициализация провайдера ASR из src.asr."""
        if self._provider is None:
            from src.asr.transcribe import get_asr_provider
            self._provider = get_asr_provider()
            if self._provider is None:
                raise RuntimeError("ASR provider not available. Check config and dependencies.")
        return self._provider

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        timestamps: bool = True,
    ) -> Dict[str, Any]:
        """
        Транскрибирует аудиофайл.

        Args:
            audio_path: Путь к WAV-файлу.
            language: Переопределение языка (если None — из конструктора или авто).
            timestamps: Включать ли временные метки сегментов.

        Returns:
            Словарь с ключами: text, segments (если timestamps), language, и др.
        """
        from src.asr.transcribe import transcribe_audio
        lang = language or self._language
        result = transcribe_audio(
            Path(audio_path),
            language=lang,
            timestamps=timestamps,
        )
        return result

    def transcribe_bytes(self, audio_pcm: bytes, sample_rate: int = 16000) -> Dict[str, Any]:
        """
        Транскрибирует сырые PCM-данные (16-bit mono).
        Сохраняет во временный файл и вызывает transcribe.
        """
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            import wave
            with wave.open(f.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_pcm)
            try:
                return self.transcribe(Path(f.name), timestamps=False)
            finally:
                Path(f.name).unlink(missing_ok=True)
