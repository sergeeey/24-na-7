"""Lightweight local benchmark smoke for episodic memory rebuilds."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.memory.episodes import rebuild_day_threads_for_day, rebuild_long_threads_for_window
from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import ensure_ingest_tables


FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "golden_memory_pipeline.json"
TMP_DB_PATH = REPO_ROOT / "tmp_pipeline_benchmark.db"


def _seed_fixture(db_path: Path) -> list[str]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    day_keys: list[str] = []
    with db.transaction():
        db.execute("DELETE FROM long_threads")
        db.execute("DELETE FROM day_threads")
        db.execute("DELETE FROM episodes")
        for day in fixture["days"]:
            day_keys.append(day["day_key"])
            for episode in day["episodes"]:
                db.execute(
                    """
                    INSERT INTO episodes (
                        id, started_at, ended_at, status, source_count, transcription_ids_json,
                        raw_text, clean_text, summary, topics_json, participants_json,
                        commitments_json, importance_score, needs_review, quality_state,
                        quality_score, quality_reasons_json, review_required, day_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode["id"],
                        episode["started_at"],
                        episode["ended_at"],
                        "summarized",
                        1,
                        "[]",
                        episode["raw_text"],
                        episode["clean_text"],
                        episode["summary"],
                        json.dumps(episode["topics"], ensure_ascii=False),
                        json.dumps(episode["participants"], ensure_ascii=False),
                        json.dumps(episode["commitments"], ensure_ascii=False),
                        episode["importance_score"],
                        0,
                        "trusted",
                        episode["importance_score"],
                        "[]",
                        0,
                        day["day_key"],
                    ),
                )
    return day_keys


def main() -> None:
    if TMP_DB_PATH.exists():
        TMP_DB_PATH.unlink()

    day_keys = _seed_fixture(TMP_DB_PATH)
    t0 = time.perf_counter()
    for day_key in day_keys:
        rebuild_day_threads_for_day(TMP_DB_PATH, day_key)
    t1 = time.perf_counter()
    rebuild_long_threads_for_window(TMP_DB_PATH, max(day_keys))
    t2 = time.perf_counter()

    db = get_reflexio_db(TMP_DB_PATH)
    day_thread_count = db.fetchone("SELECT COUNT(*) FROM day_threads")[0]
    long_thread_count = db.fetchone("SELECT COUNT(*) FROM long_threads")[0]

    result = {
        "fixture": str(FIXTURE_PATH),
        "day_count": len(day_keys),
        "day_thread_count": day_thread_count,
        "long_thread_count": long_thread_count,
        "day_thread_rebuild_ms": round((t1 - t0) * 1000, 2),
        "long_thread_rebuild_ms": round((t2 - t1) * 1000, 2),
        "total_ms": round((t2 - t0) * 1000, 2),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
