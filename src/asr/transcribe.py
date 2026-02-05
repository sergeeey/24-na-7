"""Модуль транскрипции речи (ASR) с поддержкой multiple providers."""
from pathlib import Path
from typing import Optional, Dict, Any
import os
import yaml

from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger

# Настройка логирования
setup_logging()
logger = get_logger("asr")

# Глобальный экземпляр модели (ленивая загрузка) для backward compatibility
_model: Optional[Any] = None

# Глобальный провайдер ASR
_asr_provider: Optional[Any] = None


def get_model():
    """Возвращает модель Whisper (ленивая загрузка) для backward compatibility."""
    global _model
    
    if _model is None:
        try:
            from faster_whisper import WhisperModel
            logger.info(
                "loading_model",
                model_size=settings.ASR_MODEL_SIZE,
                device=settings.ASR_DEVICE,
                compute_type=settings.ASR_COMPUTE_TYPE,
            )
            _model = WhisperModel(
                settings.ASR_MODEL_SIZE,
                device=settings.ASR_DEVICE,
                compute_type=settings.ASR_COMPUTE_TYPE,
            )
            logger.info("model_loaded")
        except ImportError:
            logger.warning("faster_whisper not available, using ASR providers")
    
    return _model


def get_asr_provider():
    """Возвращает ASR провайдер на основе конфигурации."""
    global _asr_provider
    
    if _asr_provider is None:
        # Загружаем конфигурацию
        config_path = Path("config/asr.yaml")
        edge_mode = False
        provider_name = "local"
        model_name = "faster-whisper"
        
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                provider_name = config.get("provider", "local")
                model_name = config.get("model", "faster-whisper")
                edge_mode = config.get("edge_mode", False)
                
                # Если включён edge_mode, используем distil-whisper
                if edge_mode:
                    provider_name = "distil-whisper"
                    distil_config = config.get("distil_whisper", {})
                    model_name = distil_config.get("model_size", "distil-small.en")
                    logger.info("edge_mode_enabled", provider="distil-whisper", model=model_name)
            except Exception as e:
                logger.warning("failed_to_load_asr_config", error=str(e))
                provider_name = "local"
                model_name = "faster-whisper"
        else:
            # Fallback на переменные окружения или настройки
            provider_name = os.getenv("ASR_PROVIDER", "local")
            model_name = os.getenv("ASR_MODEL", "faster-whisper")
            edge_mode = os.getenv("ASR_EDGE_MODE", "false").lower() == "true"
        
        # Импортируем и создаём провайдер
        try:
            from src.asr.providers import get_asr_provider as create_provider
            
            provider_kwargs = {}
            if provider_name == "openai":
                provider_kwargs["api_key"] = os.getenv("OPENAI_API_KEY")
            elif provider_name == "whisperx":
                provider_kwargs["model_size"] = os.getenv("WHISPERX_MODEL_SIZE", "large-v3")
                provider_kwargs["device"] = os.getenv("ASR_DEVICE", "cuda")
            elif provider_name == "parakeet":
                provider_kwargs["model_id"] = os.getenv("PARAKEET_MODEL_ID", "nvidia/parakeet-tdt-v2")
            elif provider_name == "distil-whisper":
                # Загружаем настройки distil-whisper из конфига
                if config_path.exists():
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f)
                        distil_config = config.get("distil_whisper", {})
                        provider_kwargs["model_size"] = distil_config.get("model_size", "distil-small.en")
                        provider_kwargs["device"] = distil_config.get("device", "cpu")
                else:
                    provider_kwargs["model_size"] = os.getenv("DISTIL_MODEL_SIZE", "distil-small.en")
                    provider_kwargs["device"] = os.getenv("ASR_DEVICE", "cpu")
            
            _asr_provider = create_provider(provider_name, **provider_kwargs)
            logger.info(
                "asr_provider_initialized",
                provider=provider_name,
                model=model_name,
                edge_mode=edge_mode,
            )
        except Exception as e:
            logger.error("failed_to_create_asr_provider", error=str(e), fallback="local")
            _asr_provider = None
    
    return _asr_provider


def transcribe_audio(
    audio_path: Path,
    language: Optional[str] = None,
    beam_size: int = 5,
    timestamps: bool = True,
    diarization: bool = False,
    provider: Optional[str] = None,
) -> Dict:
    """
    Транскрибирует аудиофайл с поддержкой multiple providers.
    
    Args:
        audio_path: Путь к аудиофайлу
        language: Язык (None для автоопределения)
        beam_size: Размер beam search (для local provider)
        timestamps: Включить word-level timestamps
        diarization: Включить диаризацию (требует WhisperX)
        provider: Принудительный выбор провайдера (openai|whisperx|parakeet|local)
        
    Returns:
        Словарь с текстом, языком, сегментами и метаданными
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    logger.info("transcribing", audio_path=str(audio_path), provider=provider)
    
    # Пробуем использовать новый провайдер
    asr_provider = get_asr_provider()
    
    if asr_provider and provider != "local":
        try:
            result = asr_provider.transcribe(
                audio_path=audio_path,
                language=language,
                timestamps=timestamps,
                diarization=diarization,
            )
            
            # Нормализуем формат результата
            normalized_result = {
                "text": result.get("text", ""),
                "language": result.get("language", language or "unknown"),
                "language_probability": result.get("language_probability", 1.0),
                "segments": result.get("segments", []),
                "speakers": result.get("speakers"),
                "duration": result.get("duration", 0.0),
                "provider": provider or "auto",
            }
            
            logger.info(
                "transcription_complete",
                audio_path=str(audio_path),
                language=normalized_result["language"],
                text_length=len(normalized_result["text"]),
                segments_count=len(normalized_result["segments"]),
                provider=normalized_result["provider"],
            )
            
            return normalized_result
            
        except Exception as e:
            logger.warning("asr_provider_failed", error=str(e), fallback="local")
            # Fallback на local provider
    
    # Fallback на local faster-whisper
    try:
        from faster_whisper import WhisperModel
        model = get_model()
        
        if model is None:
            raise ImportError("faster_whisper not available")
        
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
        )
        
        # Собираем все сегменты в один текст
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
        
        result = {
            "text": full_text,
            "language": info.language,
            "language_probability": info.language_probability,
            "segments": text_segments,
            "duration": info.duration,
            "provider": "local",
        }
        
        logger.info(
            "transcription_complete",
            audio_path=str(audio_path),
            language=info.language,
            text_length=len(full_text),
            segments_count=len(text_segments),
            provider="local",
        )
        
        return result
        
    except Exception as e:
        logger.error(
            "transcription_failed",
            audio_path=str(audio_path),
            error=str(e),
        )
        raise


def transcribe_file(audio_path: str | Path, **kwargs) -> Dict:
    """Удобная обёртка для транскрипции файла."""
    return transcribe_audio(Path(audio_path), **kwargs)

