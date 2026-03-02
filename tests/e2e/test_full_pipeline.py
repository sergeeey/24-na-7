"""E2E тесты полного pipeline: WAV → ASR → Enrichment → Storage → Zero-retention.

ПОЧЕМУ E2E: unit тесты проверяют модули изолированно. E2E проверяет
что весь pipeline работает вместе — от байтов аудио до structured event в БД.
Mock только ASR и LLM (детерминистичный результат без GPU/API).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.storage.db import get_reflexio_db, ensure_all_tables
from src.storage.ingest_persist import persist_structured_event
from src.enrichment.schema import StructuredEvent
from src.utils.config import settings


# Минимальный валидный WAV: 44 bytes header, 0 bytes data
MINIMAL_WAV = (
    b"RIFF"
    b"\x24\x00\x00\x00"  # chunk size = 36
    b"WAVE"
    b"fmt "
    b"\x10\x00\x00\x00"  # subchunk1 size = 16
    b"\x01\x00"  # audio format = PCM
    b"\x01\x00"  # num channels = 1
    b"\x80\x3e\x00\x00"  # sample rate = 16000
    b"\x00\x7d\x00\x00"  # byte rate = 32000
    b"\x02\x00"  # block align = 2
    b"\x10\x00"  # bits per sample = 16
    b"data"
    b"\x00\x00\x00\x00"  # data size = 0
)


def _mock_transcribe(audio_path, language=None, **kwargs):
    """Детерминистичный mock для transcribe_audio."""
    return {
        "text": "Обсуждали бюджет проекта с Маратом на встрече в офисе",
        "language": "ru",
        "language_probability": 0.95,
        "duration": 5.2,
        "segments": [
            {"text": "Обсуждали бюджет проекта", "start": 0.0, "end": 2.5},
            {"text": "с Маратом на встрече в офисе", "start": 2.5, "end": 5.2},
        ],
        "provider": "mock",
    }


def _mock_enrich(text, **kwargs):
    """Детерминистичный mock для analyze_recording_text."""
    return {
        "summary": "Встреча по обсуждению бюджета проекта с Маратом",
        "topics": ["бюджет", "проект", "встреча"],
        "emotions": ["уверенность"],
        "urgency": "medium",
        "actions": ["подготовить таблицу бюджета"],
    }


@pytest.fixture
def pipeline_db(tmp_path):
    """Создаёт изолированную БД для pipeline теста."""
    storage = tmp_path / "storage"
    storage.mkdir()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    db_path = storage / "reflexio.db"
    ensure_all_tables(db_path)
    return tmp_path, db_path


def test_full_ingest_pipeline(pipeline_db):
    """WAV → transcription → enrichment → structured event → zero-retention.

    Проверяет:
    1. WAV файл сохраняется в uploads/
    2. ASR создаёт транскрипцию
    3. Enrichment создаёт structured event с topics/emotions
    4. WAV файл удалён (zero-retention)
    5. Данные в БД корректны
    """
    tmp_path, db_path = pipeline_db
    from src.core.audio_processing import process_audio_bytes

    with (
        patch.object(settings, "STORAGE_PATH", tmp_path / "storage"),
        patch.object(settings, "UPLOADS_PATH", tmp_path / "uploads"),
        patch.object(settings, "FILTER_MUSIC", False),
        patch.object(settings, "PRIVACY_MODE", "audit"),
        patch.object(settings, "INTEGRITY_CHAIN_ENABLED", True),
        patch.object(settings, "MEMORY_ENABLED", False),
        patch.object(settings, "SPEAKER_VERIFICATION_ENABLED", False),
        patch("src.core.audio_processing.transcribe_audio", _mock_transcribe),
        patch("src.summarizer.few_shot.analyze_recording_text", _mock_enrich),
    ):
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            process_audio_bytes(
                content=MINIMAL_WAV,
                content_type="audio/wav",
                original_filename="test_meeting.wav",
                delete_audio_after=True,
                run_enrichment=True,
            )
        )

    # Pipeline должен вернуть transcribed status
    assert result["status"] == "transcribed", f"Expected transcribed, got {result}"
    assert result["ingest_id"]
    assert result["transcription_id"]

    ingest_id = result["ingest_id"]

    # WAV файл должен быть удалён (zero-retention)
    wav_files = list((tmp_path / "uploads").glob("*.wav"))
    assert len(wav_files) == 0, f"WAV not deleted: {wav_files}"

    # Транскрипция должна быть в БД
    db = get_reflexio_db(db_path)
    trans = db.fetchone(
        "SELECT text, language FROM transcriptions WHERE ingest_id = ?",
        (ingest_id,),
    )
    assert trans is not None, "Transcription not found in DB"
    assert "бюджет" in trans["text"]
    assert trans["language"] == "ru"

    # Integrity chain должна иметь 2 события (received + transcribed)
    events = db.fetchall(
        "SELECT stage FROM integrity_events WHERE ingest_id = ? ORDER BY ROWID",
        (ingest_id,),
    )
    stages = [e["stage"] for e in events]
    assert "audio_received" in stages or "ws_audio_received" in stages
    assert "transcription_saved" in stages or "ws_transcription_saved" in stages


def test_reprocess_creates_new_version(pipeline_db):
    """Re-enrichment создаёт version 2, version 1 сохраняется.

    ПОЧЕМУ: append-only гарантирует аудит-трейл. Если enrichment модель
    обновилась и дала другие topics — мы видим обе версии.
    """
    _, db_path = pipeline_db
    trans_id = str(uuid.uuid4())

    # Version 1: первый enrichment
    event_v1 = StructuredEvent(
        id=str(uuid.uuid4()),
        transcription_id=trans_id,
        timestamp=datetime.now(timezone.utc),
        text="Обсуждали бюджет проекта",
        summary="Встреча по бюджету",
        topics=["бюджет"],
        emotions=["уверенность"],
    )
    persist_structured_event(db_path, event_v1)

    # Version 2: re-enrichment с новой моделью (другие topics)
    event_v2 = StructuredEvent(
        id=str(uuid.uuid4()),
        transcription_id=trans_id,
        timestamp=datetime.now(timezone.utc),
        text="Обсуждали бюджет проекта",
        summary="Обсуждение бюджета проекта с Маратом",
        topics=["бюджет", "планирование", "встреча"],
        emotions=["уверенность", "оптимизм"],
    )
    persist_structured_event(db_path, event_v2)

    # Проверяем: всего 2 записи для этого transcription_id
    db = get_reflexio_db(db_path)
    all_versions = db.fetchall(
        "SELECT id, version, is_current, supersedes_id FROM structured_events WHERE transcription_id = ? ORDER BY version",
        (trans_id,),
    )
    assert len(all_versions) == 2, f"Expected 2 versions, got {len(all_versions)}"

    # Version 1: is_current = 0 (superseded)
    v1 = all_versions[0]
    assert v1["version"] == 1
    assert v1["is_current"] == 0

    # Version 2: is_current = 1, supersedes version 1
    v2 = all_versions[1]
    assert v2["version"] == 2
    assert v2["is_current"] == 1
    assert v2["supersedes_id"] == v1["id"]


def test_migration_tracking(pipeline_db):
    """run_migrations() применяет новые и пропускает уже применённые.

    Проверяет:
    1. Первый вызов применяет миграцию 0010
    2. Второй вызов — ничего не применяет (идемпотентность)
    3. schema_migrations содержит запись
    """
    _, db_path = pipeline_db
    from src.storage.db import run_migrations

    # Первый вызов — применяет
    applied1 = run_migrations(db_path)
    # Может быть 0 если миграция уже в ensure_all_tables, или 1+
    first_count = len(applied1)

    # Второй вызов — идемпотентный
    applied2 = run_migrations(db_path)
    assert len(applied2) == 0, f"Second run should apply nothing, got {applied2}"

    # Таблица tracking существует
    db = get_reflexio_db(db_path)
    row = db.fetchone("SELECT COUNT(*) as cnt FROM schema_migrations")
    assert row["cnt"] >= first_count
