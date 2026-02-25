"""
ASR Providers — поддержка различных провайдеров транскрипции.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
import os

from src.utils.logging import get_logger

logger = get_logger("asr.providers")


class ASRProvider(ABC):
    """Абстрактный базовый класс для ASR провайдеров."""
    
    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        timestamps: bool = True,
        diarization: bool = False,
    ) -> Dict[str, Any]:
        """
        Транскрибирует аудиофайл.
        
        Returns:
            {
                "text": str,
                "segments": List[Dict],
                "language": str,
                "speakers": Optional[List[Dict]],  # если diarization=True
            }
        """
        pass
    
    @abstractmethod
    def get_latency(self) -> float:
        """Возвращает среднюю задержку в секундах."""
        pass


class OpenAIWhisperProvider(ASRProvider):
    """Провайдер для OpenAI Whisper API (whisper-large-v3-turbo) с поддержкой кластерного режима."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        cluster_mode: bool = False,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        """
        Args:
            api_key: OpenAI API ключ
            cluster_mode: Включить кластерный режим (батчинг, retry, оптимизация)
            max_retries: Максимальное количество повторов при ошибках
            timeout: Таймаут запроса в секундах
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        try:
            import openai
            self.client = openai.OpenAI(
                api_key=self.api_key,
                timeout=timeout,
                max_retries=max_retries,
            )
        except ImportError:
            raise ImportError("openai package required. Install: pip install openai")
        
        self.cluster_mode = cluster_mode
        self.max_retries = max_retries
        self.timeout = timeout
        self._latency_history: List[float] = []
        self._request_count = 0
        self._error_count = 0
        
        if cluster_mode:
            logger.info("openai_cluster_mode_enabled", max_retries=max_retries, timeout=timeout)
    
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        timestamps: bool = True,
        diarization: bool = False,
    ) -> Dict[str, Any]:
        """Транскрибирует через OpenAI Whisper API с поддержкой кластерного режима."""
        import time
        
        start_time = time.time()
        self._request_count += 1
        
        # В кластерном режиме проверяем размер файла и оптимизируем
        if self.cluster_mode:
            file_size = audio_path.stat().st_size
            max_size_mb = 25  # OpenAI лимит
            if file_size > max_size_mb * 1024 * 1024:
                logger.warning(
                    "file_too_large_for_cluster",
                    file_size_mb=file_size / (1024 * 1024),
                    max_size_mb=max_size_mb,
                )
        
        retry_count = 0
        last_error = None
        
        while retry_count <= self.max_retries:
            try:
                with open(audio_path, "rb") as audio_file:
                    # ПОЧЕМУ whisper-1: это единственная модель Whisper в OpenAI API.
                    # "whisper-large-v3-turbo" — имя на HuggingFace, не в API.
                    response = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language,
                        response_format="verbose_json" if timestamps else "json",
                        timestamp_granularities=["word"] if timestamps else [],
                    )
                
                latency = time.time() - start_time
                self._latency_history.append(latency)
                
                result = {
                    "text": response.text,
                    "language": response.language,
                    "segments": [],
                    "cluster_mode": self.cluster_mode,
                }
                
                if hasattr(response, "words") and timestamps:
                    result["segments"] = [
                        {
                            "start": word.start,
                            "end": word.end,
                            "text": word.word,
                        }
                        for word in response.words
                    ]
                
                logger.info(
                    "openai_transcription_complete",
                    audio_path=str(audio_path),
                    latency=latency,
                    text_length=len(result["text"]),
                    cluster_mode=self.cluster_mode,
                    retry_count=retry_count,
                )
                
                return result
                
            except Exception as e:
                last_error = e
                retry_count += 1
                self._error_count += 1
                
                if retry_count <= self.max_retries:
                    wait_time = min(2 ** retry_count, 10)  # Exponential backoff, max 10 сек
                    logger.warning(
                        "openai_transcription_retry",
                        error=str(e),
                        retry_count=retry_count,
                        wait_time=wait_time,
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "openai_transcription_failed",
                        error=str(e),
                        retries_exhausted=True,
                    )
                    raise
        
        # Если дошли сюда, все ретраи исчерпаны
        raise Exception(f"OpenAI transcription failed after {self.max_retries} retries: {last_error}")
    
    def get_latency(self) -> float:
        """Средняя задержка."""
        if not self._latency_history:
            return 0.0
        return sum(self._latency_history) / len(self._latency_history)
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику провайдера (для кластерного режима)."""
        return {
            "cluster_mode": self.cluster_mode,
            "total_requests": self._request_count,
            "error_count": self._error_count,
            "success_rate": (self._request_count - self._error_count) / self._request_count if self._request_count > 0 else 0.0,
            "avg_latency": self.get_latency(),
        }


class WhisperXProvider(ASRProvider):
    """Провайдер для WhisperX (word-level timestamps + диаризация)."""
    
    def __init__(self, model_size: str = "large-v3", device: str = "cuda"):
        try:
            import whisperx
            self.whisperx = whisperx
        except ImportError:
            raise ImportError("whisperx package required. Install: pip install whisperx")
        
        self.model_size = model_size
        self.device = device
        self._model = None
        self._align_model = None
        self._diarize_model = None
        self._latency_history: List[float] = []
    
    def _load_model(self):
        """Ленивая загрузка модели."""
        if self._model is None:
            logger.info("loading_whisperx_model", model_size=self.model_size, device=self.device)
            self._model = self.whisperx.load_model(
                self.model_size,
                device=self.device,
                compute_type="float16" if self.device == "cuda" else "int8",
            )
    
    def _load_align_model(self, language: str):
        """Загрузка модели выравнивания."""
        if self._align_model is None:
            logger.info("loading_align_model", language=language)
            self._align_model, self._align_metadata = self.whisperx.load_align_model(
                language_code=language,
                device=self.device,
            )
    
    def _load_diarize_model(self):
        """Загрузка модели диаризации."""
        if self._diarize_model is None:
            logger.info("loading_diarize_model")
            try:
                self._diarize_model = self.whisperx.DiarizationPipeline(
                    use_auth_token=os.getenv("HF_TOKEN"),
                    device=self.device,
                )
            except Exception as e:
                logger.warning("diarize_model_load_failed", error=str(e))
                self._diarize_model = None
    
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        timestamps: bool = True,
        diarization: bool = False,
    ) -> Dict[str, Any]:
        """Транскрибирует через WhisperX."""
        import time
        
        start_time = time.time()
        
        self._load_model()
        
        # Транскрипция
        audio = self.whisperx.load_audio(str(audio_path))
        result = self._model.transcribe(audio, language=language)
        
        detected_language = result["language"]
        
        # Выравнивание для word-level timestamps
        if timestamps:
            self._load_align_model(detected_language)
            result = self.whisperx.align(
                result["segments"],
                self._align_model,
                self._align_metadata,
                audio,
                device=self.device,
                return_char_alignments=False,
            )
        
        # Диаризация
        if diarization:
            self._load_diarize_model()
            if self._diarize_model:
                try:
                    diarize_segments = self._diarize_model(audio, min_speakers=1, max_speakers=10)
                    result = self.whisperx.assign_word_speakers(diarize_segments, result)
                except Exception as e:
                    logger.warning("diarization_failed", error=str(e))
                    result["speakers"] = None
            else:
                logger.warning("diarization_skipped", reason="model_not_loaded")
                result["speakers"] = None
        
        latency = time.time() - start_time
        self._latency_history.append(latency)
        
        logger.info(
            "whisperx_transcription_complete",
            audio_path=str(audio_path),
            latency=latency,
            diarization=diarization,
        )
        
        return {
            "text": " ".join([seg["text"] for seg in result["segments"]]),
            "segments": result["segments"],
            "language": detected_language,
            "speakers": result.get("speakers") if diarization else None,
        }
    
    def get_latency(self) -> float:
        """Средняя задержка."""
        if not self._latency_history:
            return 0.0
        return sum(self._latency_history) / len(self._latency_history)


class DistilWhisperProvider(ASRProvider):
    """Провайдер для Distil-Whisper через CTranslate2 (офлайн режим)."""
    
    def __init__(self, model_size: str = "distil-small.en", device: str = "cpu"):
        """
        Инициализация Distil-Whisper провайдера.
        
        Args:
            model_size: "distil-small.en" | "distil-medium.en" | "distil-large-v2"
            device: "cpu" | "cuda"
        """
        try:
            import ctranslate2
            self.ctranslate2 = ctranslate2
        except ImportError:
            raise ImportError("ctranslate2 package required. Install: pip install ctranslate2")
        
        try:
            import faster_whisper
            self.faster_whisper = faster_whisper
        except ImportError:
            raise ImportError("faster-whisper package required. Install: pip install faster-whisper")
        
        self.model_size = model_size
        self.device = device
        self._model = None
        self._latency_history: List[float] = []
        self._offline_mode = True  # Всегда офлайн
    
    def _load_model(self):
        """Ленивая загрузка модели."""
        if self._model is None:
            logger.info(
                "loading_distil_whisper",
                model_size=self.model_size,
                device=self.device,
                offline_mode=True,
            )
            # Используем faster-whisper с distil моделями
            self._model = self.faster_whisper.WhisperModel(
                self.model_size,
                device=self.device,
                compute_type="int8" if self.device == "cpu" else "float16",
                download_root=None,  # Используем кэш
            )
            logger.info("distil_whisper_loaded", offline_mode=True)
    
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        timestamps: bool = True,
        diarization: bool = False,
    ) -> Dict[str, Any]:
        """Транскрибирует через Distil-Whisper (офлайн)."""
        import time
        
        start_time = time.time()
        
        self._load_model()
        
        # Транскрипция
        segments, info = self._model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,  # Встроенная VAD фильтрация
        )
        
        # Собираем сегменты
        text_segments = []
        full_text = ""
        
        for segment in segments:
            segment_text = segment.text.strip()
            text_segments.append({
                "text": segment_text,
                "start": segment.start,
                "end": segment.end,
                "confidence": getattr(segment, "avg_logprob", None),
            })
            full_text += segment_text + " "
        
        full_text = full_text.strip()
        
        latency = time.time() - start_time
        self._latency_history.append(latency)
        
        logger.info(
            "distil_whisper_transcription_complete",
            audio_path=str(audio_path),
            latency=latency,
            text_length=len(full_text),
            offline_mode=True,
        )
        
        return {
            "text": full_text,
            "segments": text_segments,
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "offline_mode": True,
        }
    
    def get_latency(self) -> float:
        """Средняя задержка."""
        if not self._latency_history:
            return 0.0
        return sum(self._latency_history) / len(self._latency_history)
    
    def is_offline(self) -> bool:
        """Проверка офлайн режима."""
        return self._offline_mode


class ParaKeetProvider(ASRProvider):
    """Провайдер для ParaKeet TDT v2 (fallback для длинных аудио)."""
    
    def __init__(self, model_id: str = "nvidia/parakeet-tdt-v2"):
        self.model_id = model_id
        self._model = None
        self._processor = None
        self._latency_history: List[float] = []
    
    def _load_model(self):
        """Ленивая загрузка модели."""
        if self._model is None:
            try:
                from transformers import AutoProcessor, AutoModelForCTC
                import torch
                
                logger.info("loading_parakeet_model", model_id=self.model_id)
                self._processor = AutoProcessor.from_pretrained(self.model_id)
                self._model = AutoModelForCTC.from_pretrained(self.model_id)
                self._model.eval()
                
                if torch.cuda.is_available():
                    self._model = self._model.cuda()
                    
            except ImportError:
                raise ImportError("transformers and torch required for ParaKeet")
    
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        timestamps: bool = True,
        diarization: bool = False,
    ) -> Dict[str, Any]:
        """Транскрибирует через ParaKeet."""
        import time
        import torch
        import librosa
        
        start_time = time.time()
        
        self._load_model()
        
        # Загрузка аудио
        audio, sr = librosa.load(str(audio_path), sr=16000)
        
        # Обработка
        inputs = self._processor(audio, sampling_rate=sr, return_tensors="pt")
        
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        
        # Инференс
        with torch.no_grad():
            logits = self._model(**inputs).logits
        
        # Декодирование
        predicted_ids = torch.argmax(logits, dim=-1)
        transcription = self._processor.batch_decode(predicted_ids)[0]
        
        latency = time.time() - start_time
        self._latency_history.append(latency)
        
        logger.info(
            "parakeet_transcription_complete",
            audio_path=str(audio_path),
            latency=latency,
        )
        
        return {
            "text": transcription,
            "segments": [],  # ParaKeet не поддерживает timestamps напрямую
            "language": language or "en",
            "speakers": None,
        }
    
    def get_latency(self) -> float:
        """Средняя задержка."""
        if not self._latency_history:
            return 0.0
        return sum(self._latency_history) / len(self._latency_history)


def get_asr_provider(provider: str = "openai", **kwargs) -> ASRProvider:
    """
    Фабричная функция для получения ASR провайдера.
    
    Args:
        provider: "openai" | "whisperx" | "parakeet" | "local" | "distil-whisper"
        **kwargs: Параметры для инициализации провайдера
        
    Returns:
        ASRProvider instance
    """
    if provider == "openai":
        return OpenAIWhisperProvider(
            api_key=kwargs.get("api_key"),
            cluster_mode=kwargs.get("cluster_mode", False),
            max_retries=kwargs.get("max_retries", 3),
            timeout=kwargs.get("timeout", 60),
        )
    elif provider == "whisperx":
        return WhisperXProvider(
            model_size=kwargs.get("model_size", "large-v3"),
            device=kwargs.get("device", "cuda"),
        )
    elif provider == "distil-whisper":
        return DistilWhisperProvider(
            model_size=kwargs.get("model_size", "distil-small.en"),
            device=kwargs.get("device", "cpu"),
        )
    elif provider == "parakeet":
        return ParaKeetProvider(model_id=kwargs.get("model_id", "nvidia/parakeet-tdt-v2"))
    elif provider == "local":
        # Используем существующий faster-whisper
        from src.asr.transcribe import transcribe_audio
        # Обёртка для совместимости
        class LocalProvider(ASRProvider):
            def transcribe(self, audio_path, language=None, timestamps=True, diarization=False):
                result = transcribe_audio(audio_path, language=language)
                return {
                    "text": result["text"],
                    "segments": result.get("segments", []),
                    "language": result.get("language", language),
                    "speakers": None,
                }
            
            def get_latency(self):
                return 0.0  # TODO: добавить отслеживание
        
        return LocalProvider()
    else:
        raise ValueError(f"Unknown provider: {provider}")

