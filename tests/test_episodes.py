from fastapi.testclient import TestClient

from src.api.main import app


def test_episode_builder_merges_close_transcriptions(tmp_path):
    from src.memory.episodes import attach_transcription_to_episode
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO ingest_queue (id, filename, file_path, file_size, status, captured_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("ing-1", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-10T12:00:00", "2026-03-10T12:00:00"),
            )
            db.execute(
                """
                INSERT INTO ingest_queue (id, filename, file_path, file_size, status, captured_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("ing-2", "b.wav", "/tmp/b.wav", 10, "transcribed", "2026-03-10T12:00:45", "2026-03-10T12:00:45"),
            )
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?)",
                ("tr-1", "ing-1", "обсудили бюджет проекта", "обсудили бюджет проекта", "2026-03-10T12:00:00"),
            )
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?)",
                ("tr-2", "ing-2", "потом сверили бюджет и сроки", "потом сверили бюджет и сроки", "2026-03-10T12:00:45"),
            )

        ep1 = attach_transcription_to_episode(db_path, "tr-1")
        ep2 = attach_transcription_to_episode(db_path, "tr-2")
        assert ep1 == ep2
        row = db.fetchone("SELECT source_count, transcription_ids_json FROM episodes WHERE id = ?", (ep1,))
        assert row["source_count"] == 2
        assert "tr-1" in row["transcription_ids_json"]
        assert "tr-2" in row["transcription_ids_json"]
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_episode_builder_splits_far_transcriptions(tmp_path):
    from src.memory.episodes import attach_transcription_to_episode
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, captured_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("ing-1", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-10T12:00:00", "2026-03-10T12:00:00"),
            )
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, captured_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("ing-2", "b.wav", "/tmp/b.wav", 10, "transcribed", "2026-03-10T12:05:00", "2026-03-10T12:05:00"),
            )
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?)",
                ("tr-1", "ing-1", "обсудили бюджет проекта", "обсудили бюджет проекта", "2026-03-10T12:00:00"),
            )
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?)",
                ("tr-2", "ing-2", "согласовали отпуск", "согласовали отпуск", "2026-03-10T12:05:00"),
            )

        ep1 = attach_transcription_to_episode(db_path, "tr-1")
        ep2 = attach_transcription_to_episode(db_path, "tr-2")
        assert ep1 != ep2
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_query_events_prefers_episodes(tmp_path):
    from src.memory.episodes import rebuild_day_threads_for_day
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:01:00",
                        "summarized",
                    2,
                    '["tr-1","tr-2"]',
                    "обсудили бюджет проекта",
                    "обсудили бюджет проекта",
                    "обсуждение бюджета",
                    '["бюджет"]',
                    '["Марат"]',
                    "[]",
                    0.9,
                    0,
                    "2026-03-10",
                ),
            )
        rebuild_day_threads_for_day(db_path, "2026-03-10")
        client = TestClient(app)
        response = client.get("/query/events", params={"q": "бюджет", "date": "2026-03-10"})
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["total"] == 1
        event = body["data"]["events"][0]
        assert event["episode_id"] == "ep-1"
        assert event["day_thread_id"]
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_day_threads_group_trusted_related_episodes(tmp_path):
    from src.memory.episodes import rebuild_day_threads_for_day, get_day_threads_for_day
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            for episode_id, started_at, summary in [
                ("ep-1", "2026-03-10T12:00:00", "обсудили бюджет проекта"),
                ("ep-2", "2026-03-10T12:20:00", "сверили бюджет и сроки проекта"),
            ]:
                db.execute(
                    """
                    INSERT INTO episodes (
                        id, started_at, ended_at, status, source_count, transcription_ids_json,
                        raw_text, clean_text, summary, topics_json, participants_json,
                        commitments_json, importance_score, needs_review, quality_state, day_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id,
                        started_at,
                        started_at,
                        "summarized",
                        1,
                        "[]",
                        summary,
                        summary,
                        summary,
                        '["бюджет","проект"]',
                        '["Марат"]',
                        '[{"text":"подготовить таблицу"}]',
                        0.9,
                        0,
                        "trusted",
                        "2026-03-10",
                    ),
                )

        rebuild_day_threads_for_day(db_path, "2026-03-10")
        threads = get_day_threads_for_day(db_path, "2026-03-10")
        assert len(threads) == 1
        thread = threads[0]
        assert thread["thread_confidence"] >= 0.7
        assert "ep-1" in thread["episode_ids_json"]
        assert "ep-2" in thread["episode_ids_json"]
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_day_threads_exclude_uncertain_episodes(tmp_path):
    from src.memory.episodes import rebuild_day_threads_for_day, get_day_threads_for_day
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, quality_state, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:00:00",
                    "summarized",
                    1,
                    "[]",
                    "сомнительный эпизод",
                    "сомнительный эпизод",
                    "сомнительный эпизод",
                    '["шум"]',
                    "[]",
                    "[]",
                    0.3,
                    1,
                    "uncertain",
                    "2026-03-10",
                ),
            )

        rebuild_day_threads_for_day(db_path, "2026-03-10")
        threads = get_day_threads_for_day(db_path, "2026-03-10")
        assert threads == []
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_digest_generator_prefers_episode_units(tmp_path):
    from src.digest.generator import DigestGenerator
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:01:30",
                    "summarized",
                    2,
                    '["tr-1","tr-2"]',
                    "обсудили бюджет и сроки проекта",
                    "обсудили бюджет и сроки проекта",
                    "созвон по бюджету",
                    '["бюджет","сроки"]',
                    '["Марат"]',
                    "[]",
                    0.8,
                    0,
                    "2026-03-10",
                ),
            )

        generator = DigestGenerator(db_path)
        digest = generator.get_daily_digest_json(__import__("datetime").date(2026, 3, 10))
        assert digest["source_unit"] == "episode"
        assert digest["episodes_used"] == 1
        assert digest["total_recordings"] == 1
        assert digest["incomplete_context"] is False
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_digest_generator_prefers_day_threads_when_available(tmp_path):
    from src.digest.generator import DigestGenerator
    from src.memory.episodes import rebuild_day_threads_for_day
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            for episode_id, started_at, summary in [
                ("ep-1", "2026-03-10T12:00:00", "обсудили бюджет проекта"),
                ("ep-2", "2026-03-10T12:10:00", "сверили бюджет и сроки проекта"),
            ]:
                db.execute(
                    """
                    INSERT INTO episodes (
                        id, started_at, ended_at, status, source_count, transcription_ids_json,
                        raw_text, clean_text, summary, topics_json, participants_json,
                        commitments_json, importance_score, needs_review, quality_state, day_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id,
                        started_at,
                        started_at,
                        "summarized",
                        1,
                        "[]",
                        summary,
                        summary,
                        summary,
                        '["бюджет"]',
                        '["Марат"]',
                        '[{"text":"подготовить таблицу"}]',
                        0.9,
                        0,
                        "trusted",
                        "2026-03-10",
                    ),
                )

        rebuild_day_threads_for_day(db_path, "2026-03-10")
        generator = DigestGenerator(db_path)
        digest = generator.get_daily_digest_json(__import__("datetime").date(2026, 3, 10))
        assert digest["source_unit"] == "day_thread"
        assert digest["thread_count"] == 1
        assert digest["episodes_used"] == 0
        assert digest["day_thread_confidence"] >= 0.7
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_digest_generator_falls_back_when_episode_not_finalized(tmp_path):
    from src.digest.generator import DigestGenerator
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:01:30",
                    "closed",
                    1,
                    '["tr-1"]',
                    "сырой эпизод",
                    "сырой эпизод",
                    "",
                    "[]",
                    "[]",
                    "[]",
                    0.4,
                    1,
                    "2026-03-10",
                ),
            )
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("ing-1", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-10T12:00:00"),
            )
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, language_probability, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("tr-1", "ing-1", "обсудили новую поставку и дедлайн", "обсудили новую поставку и дедлайн", 0.95, "2026-03-10T12:00:00"),
            )

        generator = DigestGenerator(db_path)
        digest = generator.get_daily_digest_json(__import__("datetime").date(2026, 3, 10))
        assert digest["source_unit"] == "transcription"
        assert digest["episodes_used"] == 0
        assert digest["total_recordings"] == 1
        assert digest["incomplete_context"] is True
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_digest_generator_ignores_garbage_analyses_without_trusted_units(tmp_path):
    from src.digest.generator import DigestGenerator
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("ing-1", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-10T12:00:00"),
            )
            db.execute(
                """
                INSERT INTO transcriptions (
                    id, ingest_id, text, transcript_clean, language_probability,
                    created_at, quality_state, review_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("tr-1", "ing-1", "Роман Роман ты где Роман", "Роман Роман ты где Роман", 0.99, "2026-03-10T12:00:00", "garbage", 1),
            )
            db.execute(
                """
                INSERT INTO recording_analyses (
                    id, transcription_id, summary, emotions, actions, topics, urgency, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("ra-1", "tr-1", "Шумный старый итог", "[]", "[]", "[\"шум\"]", "low", "2026-03-10T12:00:05"),
            )

        generator = DigestGenerator(db_path)
        digest = generator.get_daily_digest_json(__import__("datetime").date(2026, 3, 10))
        assert digest["total_recordings"] == 0
        assert digest["episodes_used"] == 0
        assert digest["summary_text"] == "Нет записей за день."
        assert digest["source_unit"] == "transcription"
        assert digest["evidence_strength"] == 0.0
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_contextual_transcription_risk_detects_repeated_neighbors(tmp_path):
    from src.core.audio_processing import _assess_contextual_transcription_risk
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?)",
                ("tr-1", "ing-1", "Роман Роман ты где Роман", "Роман Роман ты где Роман", "2099-03-10T12:00:00"),
            )
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?)",
                ("tr-2", "ing-2", "Роман Роман ты где Роман", "Роман Роман ты где Роман", "2099-03-10T12:00:10"),
            )
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?)",
                ("tr-3", "ing-3", "Роман Роман ты где Роман", "Роман Роман ты где Роман", "2099-03-10T12:00:20"),
            )

        flagged, reason, penalty = _assess_contextual_transcription_risk(
            db_path,
            "tr-3",
            None,
            {"text": "Роман Роман ты где Роман", "transcript_clean": "Роман Роман ты где Роман"},
        )
        assert flagged is True
        assert reason in {"repeated_phrase_pattern", "duplicate_neighbor_pattern"}
        assert penalty > 0
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_evaluate_episode_truth_marks_repeated_noise_as_garbage(tmp_path):
    from src.memory.truth import evaluate_episode_truth
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:01:00",
                    "closed",
                    1,
                    '["tr-1"]',
                    "Роман Роман ты где Роман Роман",
                    "Роман Роман ты где Роман Роман",
                    "",
                    "[]",
                    "[]",
                    "[]",
                    0.3,
                    0,
                    "2026-03-10",
                ),
            )

        truth = evaluate_episode_truth(db_path, "ep-1")
        assert truth is not None
        assert truth["quality_state"] == "garbage"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_evaluate_episode_truth_marks_low_information_as_uncertain(tmp_path):
    from src.memory.truth import evaluate_episode_truth
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:00:20",
                    "closed",
                    1,
                    '["tr-1"]',
                    "угу окей",
                    "угу окей",
                    "",
                    "[]",
                    "[]",
                    "[]",
                    0.2,
                    0,
                    "2026-03-10",
                ),
            )

        truth = evaluate_episode_truth(db_path, "ep-1")
        assert truth is not None
        assert truth["quality_state"] == "uncertain"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_evaluate_episode_truth_marks_coherent_episode_as_trusted(tmp_path):
    from src.memory.truth import evaluate_episode_truth
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:02:00",
                    "summarized",
                    2,
                    '["tr-1","tr-2"]',
                    "обсудили бюджет проекта и договорились отправить таблицу Марату",
                    "обсудили бюджет проекта и договорились отправить таблицу Марату",
                    "созвон по бюджету",
                    '["бюджет"]',
                    '["Марат"]',
                    '[{"person":"Марат","text":"отправить таблицу"}]',
                    0.9,
                    0,
                    "2026-03-10",
                ),
            )

        truth = evaluate_episode_truth(db_path, "ep-1")
        assert truth is not None
        assert truth["quality_state"] == "trusted"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_evaluate_transcription_truth_marks_repeated_noise_as_garbage(tmp_path):
    from src.memory.truth import evaluate_transcription_truth
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            for idx, created_at in enumerate(
                ["2026-03-10T12:00:00", "2026-03-10T12:00:10", "2026-03-10T12:00:20"],
                start=1,
            ):
                db.execute(
                    "INSERT INTO transcriptions (id, ingest_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        f"tr-{idx}",
                        f"ing-{idx}",
                        "Роман Роман ты где Роман",
                        "Роман Роман ты где Роман",
                        created_at,
                    ),
                )

        truth = evaluate_transcription_truth(db_path, "tr-3")
        assert truth is not None
        assert truth["quality_state"] in {"garbage", "quarantined"}
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_evaluate_transcription_truth_preserves_coherent_orphan_as_trusted(tmp_path):
    from src.memory.truth import evaluate_transcription_truth
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO transcriptions (
                    id, ingest_id, text, transcript_clean, created_at, quality_state
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "tr-1",
                    "ing-1",
                    "обсудили бюджет проекта и договорились отправить таблицу Марату",
                    "обсудили бюджет проекта и договорились отправить таблицу Марату",
                    "2026-03-10T12:00:00",
                    "trusted",
                ),
            )

        truth = evaluate_transcription_truth(db_path, "tr-1")
        assert truth is not None
        assert truth["quality_state"] == "trusted"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_run_enrichment_sync_uses_episode_text(tmp_path):
    from datetime import datetime
    from unittest.mock import patch

    from src.core.audio_processing import _run_enrichment_sync
    from src.enrichment.schema import StructuredEvent
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                "INSERT INTO ingest_queue (id, filename, file_path, file_size, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("ing-1", "a.wav", "/tmp/a.wav", 10, "transcribed", "2026-03-10T12:00:00"),
            )
            db.execute(
                "INSERT INTO transcriptions (id, ingest_id, episode_id, text, transcript_clean, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("tr-1", "ing-1", "ep-1", "короткий фрагмент", "короткий фрагмент", "2026-03-10T12:00:00"),
            )
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:01:00",
                    "open",
                    2,
                    '["tr-1","tr-2"]',
                    "полный эпизод про бюджет и согласование сроков",
                    "полный эпизод про бюджет и согласование сроков",
                    "",
                    "[]",
                    "[]",
                    "[]",
                    0.5,
                    0,
                    "2026-03-10",
                ),
            )

        captured = {}

        def fake_enrich_transcription(**kwargs):
            captured["text"] = kwargs["text"]
            return StructuredEvent(
                id="ev-1",
                transcription_id=kwargs["transcription_id"],
                episode_id=kwargs.get("episode_id"),
                timestamp=datetime(2026, 3, 10, 12, 1, 0),
                duration_sec=kwargs.get("duration_sec", 0.0),
                text=kwargs["text"],
                language="ru",
                summary="эпизод",
                topics=["бюджет"],
            )

        with patch("src.enrichment.enricher.enrich_transcription", side_effect=fake_enrich_transcription):
            _run_enrichment_sync(
                db_path=db_path,
                transcription_id="tr-1",
                result={"ingest_id": "ing-1", "episode_id": "ep-1", "duration": 2.0, "language": "ru", "text": "короткий фрагмент"},
                enrichment_text="короткий фрагмент",
                acoustic_metadata=None,
            )

        assert captured["text"] == "полный эпизод про бюджет и согласование сроков"
        row = db.fetchone("SELECT episode_id FROM structured_events WHERE id = ?", ("ev-1",))
        assert row["episode_id"] == "ep-1"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_close_stale_episodes_marks_open_as_closed(tmp_path):
    from datetime import datetime

    from src.memory.episodes import close_stale_episodes
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:00:00",
                    "open",
                    1,
                    '["tr-1"]',
                    "текст",
                    "текст",
                    "",
                    "[]",
                    "[]",
                    "[]",
                    0.5,
                    0,
                    "2026-03-10",
                ),
            )

        closed = close_stale_episodes(db_path, datetime(2026, 3, 10, 12, 5, 0))
        assert closed == 1
        row = db.fetchone("SELECT status FROM episodes WHERE id = ?", ("ep-1",))
        assert row["status"] == "closed"
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)


def test_finalize_closed_episodes_marks_summarized(tmp_path):
    from src.memory.episodes import finalize_closed_episodes
    from src.storage.db import get_reflexio_db
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.utils.config import settings

    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    old_storage = settings.STORAGE_PATH
    object.__setattr__(settings, "STORAGE_PATH", storage_path)

    try:
        db_path = storage_path / "reflexio.db"
        ensure_ingest_tables(db_path)
        db = get_reflexio_db(db_path)
        with db.transaction():
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ep-1",
                    "2026-03-10T12:00:00",
                    "2026-03-10T12:01:00",
                    "closed",
                    1,
                    '["tr-1"]',
                    "текст",
                    "текст",
                    "summary",
                    '["work"]',
                    "[]",
                    "[]",
                    0.8,
                    0,
                    "2026-03-10",
                ),
            )
            db.execute(
                """
                INSERT INTO structured_events (
                    id, transcription_id, episode_id, text, summary, topics, speakers,
                    created_at, is_current
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ev-1",
                    "tr-1",
                    "ep-1",
                    "текст",
                    "старый summary",
                    '["legacy"]',
                    '["Марат"]',
                    "2026-03-10T12:02:00",
                    1,
                ),
            )

        summarized = finalize_closed_episodes(db_path)
        assert summarized == 1
        row = db.fetchone("SELECT status FROM episodes WHERE id = ?", ("ep-1",))
        assert row["status"] == "summarized"
        current = db.fetchone(
            """
            SELECT id, text, summary, topics, is_current, version
            FROM structured_events
            WHERE episode_id = ? AND is_current = 1
            """,
            ("ep-1",),
        )
        assert current["id"] != "ev-1"
        assert current["text"] == "текст"
        assert current["summary"] == "summary"
        assert current["topics"] == '["work"]'
        assert current["version"] == 2
        previous = db.fetchone("SELECT is_current FROM structured_events WHERE id = ?", ("ev-1",))
        assert previous["is_current"] == 0
    finally:
        object.__setattr__(settings, "STORAGE_PATH", old_storage)
