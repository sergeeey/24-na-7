"""Health metrics storage for multi-sensor integration."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_health_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS health_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                steps INTEGER,
                avg_heart_rate INTEGER,
                sleep_hours REAL,
                stress_level REAL,
                source TEXT DEFAULT 'android',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_health_metrics_day ON health_metrics(day)")
        conn.commit()
    finally:
        conn.close()


def save_health_metrics(
    db_path: Path,
    day: str,
    steps: int | None,
    avg_heart_rate: int | None,
    sleep_hours: float | None,
    stress_level: float | None,
    source: str = "android",
) -> None:
    ensure_health_tables(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO health_metrics (day, steps, avg_heart_rate, sleep_hours, stress_level, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day,
                steps,
                avg_heart_rate,
                sleep_hours,
                stress_level,
                source,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_health_metrics(db_path: Path, day_from: str | None = None, day_to: str | None = None) -> list[dict[str, Any]]:
    ensure_health_tables(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if day_from and day_to:
            rows = conn.execute(
                "SELECT * FROM health_metrics WHERE day BETWEEN ? AND ? ORDER BY day DESC, id DESC",
                (day_from, day_to),
            ).fetchall()
        elif day_from:
            rows = conn.execute(
                "SELECT * FROM health_metrics WHERE day = ? ORDER BY id DESC", (day_from,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM health_metrics ORDER BY day DESC, id DESC LIMIT 200").fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()
