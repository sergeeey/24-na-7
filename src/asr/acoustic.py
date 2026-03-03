"""Lightweight acoustic feature extraction for emotion-aware enrichment.

ПОЧЕМУ этот модуль: LLM enrichment видит только текст. Но человек может
сказать "всё нормально" дрожащим голосом — текст нейтральный, акустика
кричит о стрессе. Эти фичи дают LLM второй канал данных для эмоций.

Извлекается между Stage 3 (speaker verify) и Stage 4 (ASR), пока WAV жив.
CPU-only, ~0.05-0.1с на 3-секундный сегмент.

Session aggregation: per-segment фичи шумные (3 сек — мало данных).
aggregate_session_acoustics() собирает все сегменты за период и вычисляет
статистически устойчивые метрики + внутридневные тренды.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger("asr.acoustic")

try:
    import librosa
    import numpy as np

    _LIBROSA_AVAILABLE = True
except ImportError:
    _LIBROSA_AVAILABLE = False


def extract_acoustic_features(wav_path: Path | str, sr: int = 16000) -> dict[str, Any] | None:
    """Extract pitch, energy, spectral centroid from WAV file.

    Returns None if librosa unavailable or extraction fails (graceful degradation).
    """
    if not _LIBROSA_AVAILABLE:
        return None

    try:
        y, actual_sr = librosa.load(str(wav_path), sr=sr)

        if len(y) < sr * 0.3:
            # < 0.3с аудио — слишком мало для надёжных фич
            return None

        # 1. Pitch (F0) через YIN — быстрее pyin в 10x, для эвристики хватает
        f0 = librosa.yin(y, fmin=65, fmax=300, sr=actual_sr)
        valid_f0 = f0[(f0 > 0) & (f0 < 300)]

        if len(valid_f0) < 3:
            # Слишком мало voiced frames — нельзя оценить pitch
            return None

        pitch_mean = float(np.mean(valid_f0))
        pitch_std = float(np.std(valid_f0))

        # 2. RMS Energy (громкость / экспрессия)
        rms = librosa.feature.rms(y=y)[0]
        energy_mean = float(np.mean(rms))

        # 3. Spectral Centroid (яркость голоса)
        # ПОЧЕМУ: высокий centroid = напряжённый/возбуждённый, низкий = расслабленный
        centroid = librosa.feature.spectral_centroid(y=y, sr=actual_sr)[0]
        centroid_mean = float(np.mean(centroid))

        # Эвристика возбуждения: высокая вариативность тона + громкость
        is_agitated = pitch_std > 30 and energy_mean > 0.03
        is_low_energy = energy_mean < 0.01 and pitch_std < 15

        if is_agitated:
            arousal = "high"
        elif is_low_energy:
            arousal = "low"
        else:
            arousal = "normal"

        result = {
            "pitch_hz_mean": round(pitch_mean, 1),
            "pitch_variance": round(pitch_std, 1),
            "energy_mean": round(energy_mean, 4),
            "spectral_centroid_mean": round(centroid_mean, 1),
            "acoustic_arousal": arousal,
        }

        logger.debug(
            "acoustic_features_extracted",
            pitch=result["pitch_hz_mean"],
            variance=result["pitch_variance"],
            arousal=arousal,
        )
        return result

    except Exception as e:
        logger.warning("acoustic_extraction_failed", error=str(e), path=str(wav_path))
        return None


def aggregate_session_acoustics(
    db_path: Path,
    target_date: date,
    hour_buckets: bool = True,
) -> dict[str, Any] | None:
    """Aggregate per-segment acoustic features into session-level profile.

    ПОЧЕМУ нужна агрегация: pitch_variance одного 3-секундного сегмента
    имеет CI шириной ±20 Гц — слишком шумно. Но mean(pitch_variance) по
    30+ сегментам за утро vs вечер — это надёжный тренд.

    Returns:
        {
            "total_segments": int,
            "day_profile": { pitch_hz_mean, pitch_variance_mean, energy_mean, ... },
            "arousal_distribution": { "high": 12, "normal": 45, "low": 3 },
            "hourly_trend": [ { "hour": "09", "arousal": "normal", ... }, ... ],
            "stress_periods": [ { "hour": "15", "reason": "pitch spike" }, ... ],
        }
    """
    from src.storage.db import get_reflexio_db

    try:
        db = get_reflexio_db(db_path)
    except Exception:
        return None

    rows = db.fetchall(
        """
        SELECT pitch_hz_mean, pitch_variance, energy_mean,
               spectral_centroid_mean, acoustic_arousal, created_at
        FROM structured_events
        WHERE DATE(created_at) = ? AND is_current = 1
              AND pitch_hz_mean IS NOT NULL
        ORDER BY created_at ASC
        """,
        (target_date.isoformat(),),
    )

    if not rows or len(rows) < 3:
        return None

    pitches = [float(r["pitch_hz_mean"]) for r in rows if r["pitch_hz_mean"]]
    variances = [float(r["pitch_variance"]) for r in rows if r["pitch_variance"]]
    energies = [float(r["energy_mean"]) for r in rows if r["energy_mean"]]
    centroids = [float(r["spectral_centroid_mean"]) for r in rows if r["spectral_centroid_mean"]]

    if not pitches:
        return None

    def _safe_mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def _safe_std(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        m = _safe_mean(vals)
        return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))

    # Day-level profile (статистически устойчивый)
    day_profile = {
        "pitch_hz_mean": round(_safe_mean(pitches), 1),
        "pitch_hz_std": round(_safe_std(pitches), 1),
        "pitch_variance_mean": round(_safe_mean(variances), 1),
        "energy_mean": round(_safe_mean(energies), 4),
        "energy_std": round(_safe_std(energies), 4),
        "spectral_centroid_mean": round(_safe_mean(centroids), 1),
    }

    # Arousal distribution
    arousal_dist: dict[str, int] = {"high": 0, "normal": 0, "low": 0}
    for r in rows:
        a = (r["acoustic_arousal"] or "normal").lower()
        if a in arousal_dist:
            arousal_dist[a] += 1

    total = sum(arousal_dist.values()) or 1
    dominant_arousal = max(arousal_dist, key=lambda k: arousal_dist[k])

    # ПОЧЕМУ hourly trend: показывает КОГДА стресс нарастает/спадает.
    # "Утром спокоен, после 15:00 возбуждён" → actionable insight.
    hourly_trend: list[dict[str, Any]] = []
    stress_periods: list[dict[str, str]] = []

    if hour_buckets:
        by_hour: dict[str, list[dict]] = {}
        for r in rows:
            ts = r["created_at"] or ""
            hour = ts[11:13] if len(ts) >= 13 else "??"
            by_hour.setdefault(hour, []).append(r)

        for hour in sorted(by_hour.keys()):
            h_rows = by_hour[hour]
            h_vars = [float(r["pitch_variance"]) for r in h_rows if r["pitch_variance"]]
            h_energies = [float(r["energy_mean"]) for r in h_rows if r["energy_mean"]]
            h_arousals = [r["acoustic_arousal"] or "normal" for r in h_rows]

            high_count = sum(1 for a in h_arousals if a == "high")
            hour_arousal = "high" if high_count > len(h_arousals) * 0.5 else (
                "low" if all(a == "low" for a in h_arousals) else "normal"
            )

            bucket = {
                "hour": hour,
                "segments": len(h_rows),
                "pitch_variance_mean": round(_safe_mean(h_vars), 1),
                "energy_mean": round(_safe_mean(h_energies), 4),
                "arousal": hour_arousal,
            }
            hourly_trend.append(bucket)

            # Детекция стресс-периодов: pitch variance > day_mean + 1.5σ
            if h_vars and day_profile["pitch_variance_mean"] > 0:
                threshold = day_profile["pitch_variance_mean"] + 1.5 * _safe_std(variances)
                if _safe_mean(h_vars) > threshold:
                    stress_periods.append({
                        "hour": hour,
                        "reason": f"pitch variance spike ({_safe_mean(h_vars):.0f} > {threshold:.0f} Hz)",
                    })

    result = {
        "date": target_date.isoformat(),
        "total_segments": len(rows),
        "day_profile": day_profile,
        "dominant_arousal": dominant_arousal,
        "arousal_distribution": arousal_dist,
        "arousal_high_pct": round(arousal_dist["high"] / total * 100, 1),
        "hourly_trend": hourly_trend,
        "stress_periods": stress_periods,
    }

    logger.info(
        "session_acoustics_aggregated",
        date=target_date.isoformat(),
        segments=len(rows),
        dominant=dominant_arousal,
        high_pct=result["arousal_high_pct"],
        stress_hours=len(stress_periods),
    )
    return result
