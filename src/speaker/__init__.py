"""Speaker verification module — определяет, является ли спикер пользователем.

Использование:
    from src.speaker import verify_speaker, enroll_from_wavs
    from src.speaker.storage import ensure_speaker_tables, has_active_profile

Архитектура:
    amplitude.py  — Уровень 1: RMS gate (~0.1ms)
    embedder.py   — resemblyzer singleton (GE2E LSTM 256-dim, ~50ms/segment)
    verifier.py   — Уровень 2: cosine similarity
    storage.py    — SQLite: voice_profiles + transcriptions speaker columns
    models.py     — VerificationResult, SpeakerProfile dataclasses
    enrollment.py — утилита для enrollment из WAV файлов
"""
from .models import SpeakerProfile, VerificationResult
from .verifier import verify_speaker
from .amplitude import passes_amplitude_gate, compute_rms
from .storage import ensure_speaker_tables, save_voice_profile, has_active_profile

__all__ = [
    "SpeakerProfile",
    "VerificationResult",
    "verify_speaker",
    "passes_amplitude_gate",
    "compute_rms",
    "ensure_speaker_tables",
    "save_voice_profile",
    "has_active_profile",
]
