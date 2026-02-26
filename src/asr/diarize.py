"""
Speaker Diarization — обёртка над pyannote.audio 3.1.

ПОЧЕМУ pyannote:
  pyannote.audio — де-факто стандарт CPU-diarization в 2024.
  pipeline("pyannote/speaker-diarization-3.1") даёт DER ~5% на обычных
  разговорных записях, работает CPU-only.

Требования:
  - HF_TOKEN в .env (принять лицензию модели на huggingface.co/pyannote)
  - pip install pyannote.audio>=3.1.0

Lazy load:
  Модель загружается при первом вызове, ~2GB скачивается один раз.
  Если pyannote не установлен — бросаем DiarizationNotAvailableError,
  остальной код продолжает работать без диаризации.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from src.persongraph.anchor import DiarizedSegment
from src.utils.logging import get_logger

logger = get_logger("asr.diarize")

# ──────────────────────────────────────────────
# Исключения
# ──────────────────────────────────────────────


class DiarizationNotAvailableError(RuntimeError):
    """Поднимается если pyannote.audio не установлен или HF_TOKEN не задан."""


# ──────────────────────────────────────────────
# Глобальный pipeline (ленивая инициализация)
# ──────────────────────────────────────────────

_pipeline = None  # type: ignore[var-annotated]
_pipeline_loaded: bool = False


def _load_pipeline():  # type: ignore[return]
    """
    Загружает pyannote pipeline. Вызывается один раз при первой диаризации.

    ПОЧЕМУ глобальный singleton: модель весит ~600MB в RAM.
    Загружать заново на каждый аудио-файл — недопустимо (~5 сек).
    """
    global _pipeline, _pipeline_loaded

    if _pipeline_loaded:
        return _pipeline

    _pipeline_loaded = True  # флаг чтобы не пытаться повторно при ошибке

    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        logger.warning(
            "diarize_disabled",
            reason="HF_TOKEN not set — speaker diarization unavailable",
        )
        return None

    try:
        from pyannote.audio import Pipeline  # type: ignore[import-untyped]

        logger.info("diarize_pipeline_loading", model="pyannote/speaker-diarization-3.1")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        logger.info("diarize_pipeline_ready")
        return _pipeline

    except ImportError:
        logger.warning(
            "diarize_disabled",
            reason="pyannote.audio not installed",
        )
        return None
    except Exception as e:
        logger.error("diarize_pipeline_failed", error=str(e))
        return None


# ──────────────────────────────────────────────
# Публичный API
# ──────────────────────────────────────────────


def diarize_audio(
    audio_path: Path,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
) -> list[DiarizedSegment]:
    """
    Диаризует аудиофайл — разделяет по спикерам.

    Args:
        audio_path:   Путь к WAV-файлу (16kHz, mono рекомендуется)
        min_speakers: Минимальное число спикеров (None = автоопределение)
        max_speakers: Максимальное число спикеров (None = автоопределение)

    Returns:
        Список DiarizedSegment с меткой спикера, start, end.
        Пустой список если диаризация недоступна.

    Raises:
        FileNotFoundError: если аудио-файл не существует
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    pipeline = _load_pipeline()
    if pipeline is None:
        logger.debug("diarize_skipped", reason="pipeline not available")
        return []

    try:
        logger.info("diarize_start", path=str(audio_path))

        # ПОЧЕМУ kwargs: pyannote 3.1 принимает min/max_speakers опционально.
        # Если не задаём — модель сама определяет число спикеров.
        kwargs: dict = {}
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

        diarization = pipeline(str(audio_path), **kwargs)

        segments: list[DiarizedSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                DiarizedSegment(
                    speaker=speaker,        # "SPEAKER_00", "SPEAKER_01", ...
                    start=turn.start,
                    end=turn.end,
                )
            )

        logger.info(
            "diarize_done",
            path=str(audio_path),
            segments=len(segments),
            speakers=len({s.speaker for s in segments}),
        )
        return segments

    except Exception as e:
        logger.error("diarize_failed", path=str(audio_path), error=str(e))
        return []


def is_diarization_available() -> bool:
    """Проверяет доступность диаризации (для /health endpoint)."""
    pipeline = _load_pipeline()
    return pipeline is not None
