"""Модуль транскрипции речи (ASR) с поддержкой multiple providers."""
import threading
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
_model_lock = threading.Lock()

# Глобальный провайдер ASR
_asr_provider: Optional[Any] = None
_asr_provider_initialized: bool = False
_asr_lock = threading.Lock()


def get_model():
    """Возвращает модель Whisper (ленивая загрузка) для backward compatibility."""
    global _model

    # ПОЧЕМУ double-check: WhisperModel загружается ~5 сек и ~600MB RAM.
    # Без lock два concurrent запроса загрузят модель дважды.
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
            logger.info(
                "loading_model",
                model_size=settings.ASR_MODEL_SIZE,
                device=settings.ASR_DEVICE,
                compute_type=settings.ASR_COMPUTE_TYPE,
            )
            # ПОЧЕМУ cpu_threads=2, num_workers=1:
            # ctranslate2 без лимита спавнит N*CPU_COUNT процессов (spawn_main).
            # При 2 uvicorn workers × N записей → каждая транскрипция → N процессов.
            # Накапливаются, жрут 200-400% CPU, блокируют event loop.
            # cpu_threads=2: ctranslate2 использует 2 треда вместо всех ядер.
            # num_workers=1: только один параллельный decode worker в модели.
            _model = WhisperModel(
                settings.ASR_MODEL_SIZE,
                device=settings.ASR_DEVICE,
                compute_type=settings.ASR_COMPUTE_TYPE,
                cpu_threads=2,
                num_workers=1,
            )
            logger.info("model_loaded")
        except ImportError:
            logger.warning("faster_whisper not available, using ASR providers")

    return _model


def get_asr_provider():
    """Возвращает ASR провайдер на основе конфигурации."""
    global _asr_provider, _asr_provider_initialized

    # ПОЧЕМУ отдельный флаг: для local provider _asr_provider = None (нет обёртки).
    # Без флага каждый вызов заново читал бы yaml и логировал инициализацию.
    if _asr_provider_initialized:
        return _asr_provider

    with _asr_lock:
        if _asr_provider_initialized:
            return _asr_provider
        # Загружаем конфигурацию.
        # Приоритет: Settings (src.utils.config) > config/asr.yaml > env.
        # Для local faster-whisper всегда используются Settings: ASR_MODEL_SIZE, ASR_DEVICE,
        # ASR_COMPUTE_TYPE, ASR_LANGUAGE. Провайдер (provider/model/edge_mode) задаётся YAML или env.
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

        # ПОЧЕМУ provider=="local" → None: LocalProvider обёртка вызывает
        # transcribe_audio() → get_asr_provider() → LocalProvider → бесконечная рекурсия.
        # Для local просто пропускаем обёртку, transcribe_audio() сама вызовет faster-whisper.
        if provider_name == "local":
            _asr_provider = None
            logger.info(
                "asr_provider_initialized",
                provider="local",
                model=model_name,
                edge_mode=edge_mode,
            )
        else:
            try:
                from src.asr.providers import get_asr_provider as create_provider

                provider_kwargs = {}
                if provider_name == "openai":
                    provider_kwargs["api_key"] = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
                elif provider_name == "whisperx":
                    provider_kwargs["model_size"] = os.getenv("WHISPERX_MODEL_SIZE", "large-v3")
                    provider_kwargs["device"] = getattr(settings, "ASR_DEVICE", None) or os.getenv("ASR_DEVICE", "cuda")
                elif provider_name == "parakeet":
                    provider_kwargs["model_id"] = os.getenv("PARAKEET_MODEL_ID", "nvidia/parakeet-tdt-v2")
                elif provider_name == "distil-whisper":
                    if config_path.exists():
                        with open(config_path, "r", encoding="utf-8") as f:
                            config = yaml.safe_load(f)
                            distil_config = config.get("distil_whisper", {})
                            provider_kwargs["model_size"] = distil_config.get("model_size", "distil-small.en")
                            provider_kwargs["device"] = distil_config.get("device", "cpu")
                    else:
                        provider_kwargs["model_size"] = os.getenv("DISTIL_MODEL_SIZE", "distil-small.en")
                        provider_kwargs["device"] = getattr(settings, "ASR_DEVICE", None) or os.getenv("ASR_DEVICE", "cpu")

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

        _asr_provider_initialized = True

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
        # Fallback на OpenAI Whisper при падении локального ASR (через requests, без openai.Client — обход proxies)
        api_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                import requests
                with open(audio_path, "rb") as f:
                    body = {"file": (audio_path.name, f, "audio/wav")}
                    data = {"model": "whisper-1"}
                    if language:
                        data["language"] = language
                    r = requests.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        files=body,
                        data=data,
                        timeout=60,
                    )
                r.raise_for_status()
                out = r.json()
                normalized = {
                    "text": out.get("text", ""),
                    "language": out.get("language", language or "unknown"),
                    "language_probability": 1.0,
                    "segments": [],
                    "duration": 0.0,
                    "provider": "openai_fallback",
                }
                logger.info("transcription_complete", audio_path=str(audio_path), provider="openai_fallback", text_length=len(normalized["text"]))
                return normalized
            except Exception as fallback_e:
                logger.warning("openai_fallback_failed", error=str(fallback_e))
        raise


def transcribe_file(audio_path: str | Path, **kwargs) -> Dict:
    """Удобная обёртка для транскрипции файла."""
    return transcribe_audio(Path(audio_path), **kwargs)


