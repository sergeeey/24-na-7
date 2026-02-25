"""Тесты для speaker verification модуля.

Тестируем без resemblyzer (heavy LSTM model) — мокируем embedder.
ПОЧЕМУ mock: CI/CD не должен зависеть от 18MB модели и GPU.
Тестируем бизнес-логику: cosine similarity, amplitude gate, storage, enrollment.
"""
from __future__ import annotations

import json
import sqlite3
import wave
import struct
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def db_path(tmp_path) -> Path:
    """Временная SQLite БД для тестов."""
    return tmp_path / "test_speaker.db"


@pytest.fixture
def client():
    """TestClient для API тестов voice endpoints."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


@pytest.fixture
def sample_embedding() -> np.ndarray:
    """Тестовый 256-dim embedding (нормализованный на единичную сферу)."""
    np.random.seed(42)
    emb = np.random.randn(256).astype(np.float32)
    return emb / np.linalg.norm(emb)  # нормализуем


@pytest.fixture
def silent_audio() -> np.ndarray:
    """Тихий аудио-сигнал (ниже amplitude threshold)."""
    return np.zeros(16000, dtype=np.float32)


@pytest.fixture
def loud_speech_audio() -> np.ndarray:
    """Громкий синусоидальный сигнал (имитирует речь по амплитуде)."""
    t = np.linspace(0, 1.0, 16000, dtype=np.float32)
    return 0.3 * np.sin(2 * np.pi * 440 * t)


def _make_wav(tmp_path: Path, audio: np.ndarray, sr: int = 16000) -> Path:
    """Создаёт WAV файл из numpy массива float32 [-1, 1]."""
    wav_path = tmp_path / f"sample_{id(audio)}.wav"
    pcm = (audio * 32768).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return wav_path


# ═══════════════════════════════════════════════════════════════════════════
# amplitude.py tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAmplitude:
    def test_compute_rms_silence(self):
        from src.speaker.amplitude import compute_rms
        audio = np.zeros(16000, dtype=np.float32)
        assert compute_rms(audio) == 0.0

    def test_compute_rms_sine(self):
        from src.speaker.amplitude import compute_rms
        # Синус амплитудой 0.5 → RMS = 0.5/sqrt(2) ≈ 0.354
        t = np.linspace(0, 1.0, 16000, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        rms = compute_rms(audio)
        assert abs(rms - 0.5 / (2 ** 0.5)) < 0.01

    def test_compute_rms_empty(self):
        from src.speaker.amplitude import compute_rms
        assert compute_rms(np.array([], dtype=np.float32)) == 0.0

    def test_amplitude_gate_silent_fails(self, silent_audio):
        from src.speaker.amplitude import passes_amplitude_gate
        assert passes_amplitude_gate(silent_audio, threshold=0.01) is False

    def test_amplitude_gate_loud_passes(self, loud_speech_audio):
        from src.speaker.amplitude import passes_amplitude_gate
        assert passes_amplitude_gate(loud_speech_audio, threshold=0.01) is True

    def test_amplitude_gate_custom_threshold(self, loud_speech_audio):
        from src.speaker.amplitude import passes_amplitude_gate
        # Очень высокий порог — тест сигнал не проходит
        assert passes_amplitude_gate(loud_speech_audio, threshold=10.0) is False


# ═══════════════════════════════════════════════════════════════════════════
# verifier.py — cosine similarity
# ═══════════════════════════════════════════════════════════════════════════

class TestCosineSimilarity:
    def test_identical_vectors(self, sample_embedding):
        from src.speaker.verifier import cosine_similarity
        # Один и тот же вектор → similarity = 1.0
        sim = cosine_similarity(sample_embedding, sample_embedding)
        assert abs(sim - 1.0) < 1e-5

    def test_orthogonal_vectors(self):
        from src.speaker.verifier import cosine_similarity
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        sim = cosine_similarity(a, b)
        assert abs(sim - 0.0) < 1e-5

    def test_opposite_vectors(self):
        from src.speaker.verifier import cosine_similarity
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        sim = cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-5

    def test_zero_vector(self):
        from src.speaker.verifier import cosine_similarity
        a = np.zeros(256, dtype=np.float32)
        b = np.ones(256, dtype=np.float32)
        # Нулевой вектор → 0.0 (без деления на 0)
        assert cosine_similarity(a, b) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# storage.py tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSpeakerStorage:
    def test_ensure_speaker_tables_creates_tables(self, db_path):
        from src.speaker.storage import ensure_speaker_tables
        ensure_speaker_tables(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "voice_profiles" in tables

    def test_ensure_speaker_tables_idempotent(self, db_path):
        """Повторный вызов не должен падать (ALTER TABLE duplicate column)."""
        from src.speaker.storage import ensure_speaker_tables
        ensure_speaker_tables(db_path)
        ensure_speaker_tables(db_path)  # Второй вызов — без ошибок

    def test_save_and_load_profile(self, db_path, sample_embedding):
        from src.speaker.storage import save_voice_profile, load_active_profile_embedding
        ensure_tables_for_test(db_path)

        profile_id = save_voice_profile(db_path, sample_embedding, user_id="test_user")
        assert profile_id

        loaded = load_active_profile_embedding(db_path, "test_user")
        assert loaded is not None
        assert loaded.shape == (256,)
        # Должны быть близки (потеря точности при JSON round-trip)
        assert np.allclose(loaded, sample_embedding, atol=1e-5)

    def test_save_profile_deactivates_old(self, db_path, sample_embedding):
        """При сохранении нового профиля старый должен деактивироваться."""
        from src.speaker.storage import save_voice_profile, load_active_profile_embedding
        ensure_tables_for_test(db_path)

        np.random.seed(1)
        emb1 = np.random.randn(256).astype(np.float32)
        emb2 = sample_embedding

        save_voice_profile(db_path, emb1, user_id="u1")
        save_voice_profile(db_path, emb2, user_id="u1")

        # Должен вернуть последний (emb2)
        loaded = load_active_profile_embedding(db_path, "u1")
        assert np.allclose(loaded, emb2, atol=1e-5)

        # В БД должна быть только одна активная запись
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM voice_profiles WHERE user_id='u1' AND is_active=1"
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_load_nonexistent_profile_returns_none(self, db_path):
        from src.speaker.storage import load_active_profile_embedding, ensure_speaker_tables
        ensure_speaker_tables(db_path)
        result = load_active_profile_embedding(db_path, "nonexistent_user")
        assert result is None

    def test_has_active_profile(self, db_path, sample_embedding):
        from src.speaker.storage import has_active_profile, save_voice_profile
        ensure_tables_for_test(db_path)

        assert has_active_profile(db_path, "u2") is False
        save_voice_profile(db_path, sample_embedding, user_id="u2")
        assert has_active_profile(db_path, "u2") is True


# ═══════════════════════════════════════════════════════════════════════════
# verifier.py — full verify_speaker (mock embedder)
# ═══════════════════════════════════════════════════════════════════════════

class TestVerifySpeaker:
    def test_silent_audio_returns_not_user(self, db_path, silent_audio):
        from src.speaker.verifier import verify_speaker
        ensure_tables_for_test(db_path)

        result = verify_speaker(
            audio=silent_audio,
            db_path=db_path,
            amplitude_threshold=0.01,
        )
        assert result.is_user is False
        assert result.method == "amplitude_filtered"
        assert result.confidence == 0.0

    def test_no_profile_fail_open(self, db_path, loud_speech_audio):
        """Без профиля — fail-open (считаем пользователем)."""
        from src.speaker.storage import ensure_speaker_tables
        from src.speaker.verifier import verify_speaker
        ensure_speaker_tables(db_path)

        result = verify_speaker(loud_speech_audio, db_path=db_path)
        assert result.is_user is True
        assert result.method == "no_profile"

    def test_matching_speaker_passes(self, db_path, loud_speech_audio, sample_embedding):
        """Голос совпадает с профилем → is_user=True."""
        from src.speaker.storage import save_voice_profile
        from src.speaker.verifier import verify_speaker
        ensure_tables_for_test(db_path)
        save_voice_profile(db_path, sample_embedding, user_id="default")

        # ПОЧЕМУ патчим src.speaker.embedder.embed_audio, а не verifier.embed_audio:
        # embed_audio импортируется внутри функции (lazy import), поэтому
        # patch должен перехватить имя в модуле embedder, а не в verifier.
        with patch("src.speaker.embedder.embed_audio", return_value=sample_embedding):
            result = verify_speaker(
                audio=loud_speech_audio,
                db_path=db_path,
                similarity_threshold=0.75,
            )
        assert result.is_user is True
        assert result.confidence > 0.99
        assert result.method == "embedding"

    def test_different_speaker_blocked(self, db_path, loud_speech_audio, sample_embedding):
        """Другой голос → is_user=False."""
        from src.speaker.storage import save_voice_profile
        from src.speaker.verifier import verify_speaker
        ensure_tables_for_test(db_path)
        save_voice_profile(db_path, sample_embedding, user_id="default")

        # Другой embedding — перпендикулярный профилю (similarity ≈ 0)
        np.random.seed(99)
        different_emb = np.random.randn(256).astype(np.float32)
        different_emb = different_emb / np.linalg.norm(different_emb)

        with patch("src.speaker.embedder.embed_audio", return_value=different_emb):
            result = verify_speaker(
                audio=loud_speech_audio,
                db_path=db_path,
                similarity_threshold=0.75,
            )
        assert result.is_user is False
        assert result.speaker_id == 0
        assert result.method == "embedding"

    def test_embedder_error_fail_open(self, db_path, loud_speech_audio, sample_embedding):
        """При ошибке embedder — fail-open (не теряем запись)."""
        from src.speaker.storage import save_voice_profile
        from src.speaker.verifier import verify_speaker
        ensure_tables_for_test(db_path)
        save_voice_profile(db_path, sample_embedding)

        with patch("src.speaker.embedder.embed_audio", side_effect=RuntimeError("LSTM crashed")):
            result = verify_speaker(loud_speech_audio, db_path=db_path)
        assert result.is_user is True


# ═══════════════════════════════════════════════════════════════════════════
# enrollment.py tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEnrollment:
    def test_enrollment_too_few_samples(self, tmp_path, db_path):
        from src.speaker.enrollment import enroll_from_wavs
        ensure_tables_for_test(db_path)

        # Только 1 образец — должен поднять ValueError
        audio = 0.3 * np.ones(16000, dtype=np.float32)
        wav_path = _make_wav(tmp_path, audio)

        with pytest.raises(ValueError, match="at least 3"):
            enroll_from_wavs([wav_path], db_path)

    def test_enrollment_too_short_sample(self, tmp_path, db_path):
        from src.speaker.enrollment import enroll_from_wavs, MIN_DURATION_SECONDS
        ensure_tables_for_test(db_path)

        # 0.5 секунд — слишком коротко
        short_audio = 0.3 * np.ones(8000, dtype=np.float32)  # 0.5s at 16kHz
        paths = [_make_wav(tmp_path, short_audio) for _ in range(3)]

        with pytest.raises(ValueError, match="too short"):
            enroll_from_wavs(paths, db_path)

    def test_enrollment_creates_profile(self, tmp_path, db_path, sample_embedding):
        """Успешный enrollment создаёт профиль в БД."""
        from src.speaker.enrollment import enroll_from_wavs
        from src.speaker.storage import has_active_profile
        ensure_tables_for_test(db_path)

        # Достаточно длинные образцы (3 секунды, 0.3 амплитуда)
        audio = 0.3 * np.ones(48000, dtype=np.float32)  # 3s at 16kHz
        paths = [_make_wav(tmp_path, audio) for _ in range(3)]

        # Мокируем embed_audio (не загружаем реальную модель)
        with patch("src.speaker.enrollment.embed_audio", return_value=sample_embedding):
            result = enroll_from_wavs(paths, db_path, user_id="test_enroll")

        assert result["profile_id"]
        assert result["sample_count"] == 3
        assert result["user_id"] == "test_enroll"
        assert has_active_profile(db_path, "test_enroll")

    def test_enrollment_mean_embedding(self, tmp_path, db_path):
        """Mean embedding должен быть средним арифметическим всех образцов."""
        from src.speaker.enrollment import enroll_from_wavs
        from src.speaker.storage import load_active_profile_embedding
        ensure_tables_for_test(db_path)

        audio = 0.3 * np.ones(48000, dtype=np.float32)
        paths = [_make_wav(tmp_path, audio) for _ in range(3)]

        np.random.seed(42)
        emb1 = np.random.randn(256).astype(np.float32)
        emb2 = np.random.randn(256).astype(np.float32)
        emb3 = np.random.randn(256).astype(np.float32)
        expected_mean = np.mean([emb1, emb2, emb3], axis=0).astype(np.float32)

        call_count = [0]
        embeddings = [emb1, emb2, emb3]

        def mock_embed(audio, sr):
            idx = call_count[0]
            call_count[0] += 1
            return embeddings[idx]

        with patch("src.speaker.enrollment.embed_audio", side_effect=mock_embed):
            enroll_from_wavs(paths, db_path, user_id="mean_test")

        loaded = load_active_profile_embedding(db_path, "mean_test")
        assert np.allclose(loaded, expected_mean, atol=1e-4)


# ═══════════════════════════════════════════════════════════════════════════
# API endpoint tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVoiceEnrollEndpoint:
    def test_enroll_too_few_files(self, client):
        """Менее 3 файлов → 400."""
        audio = 0.3 * np.ones(48000, dtype=np.float32)
        pcm = (audio * 32768).astype(np.int16).tobytes()
        # WAV header + data
        wav_content = _make_wav_bytes(pcm, sr=16000)

        resp = client.post(
            "/voice/enroll",
            files=[("files", ("s1.wav", wav_content, "audio/wav"))],
        )
        assert resp.status_code == 400
        assert "at least 3" in resp.json()["detail"]

    def test_enroll_invalid_file(self, client):
        """Не WAV файл → 400."""
        files = [
            ("files", (f"s{i}.wav", b"not a wav file", "audio/wav"))
            for i in range(3)
        ]
        resp = client.post("/voice/enroll", files=files)
        assert resp.status_code == 400

    def test_enrollment_status_no_profile(self, client):
        """GET /voice/enroll/status без профиля → has_profile=False."""
        resp = client.get("/voice/enroll/status?user_id=nonexistent_xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_profile"] is False
        assert "user_id" in data


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def ensure_tables_for_test(db_path: Path):
    """Инициализирует нужные таблицы для тестов speaker модуля."""
    from src.speaker.storage import ensure_speaker_tables
    from src.storage.ingest_persist import ensure_ingest_tables
    ensure_ingest_tables(db_path)
    ensure_speaker_tables(db_path)


def _make_wav_bytes(pcm_bytes: bytes, sr: int = 16000) -> bytes:
    """Создаёт валидный WAV в памяти (RIFF/WAVE header + PCM data)."""
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()
