"""Health metrics storage for multi-sensor integration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.storage.db import get_reflexio_db


def ensure_health_tables(db_path: Path) -> None:
    """Создаёт таблицу и индекс для health_metrics, если не существуют."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)
    # ПОЧЕМУ: DDL (CREATE TABLE / CREATE INDEX) не оборачивается в transaction() —
    # SQLite автоматически фиксирует DDL, а явный BEGIN DEFERRED может вызвать
    # "cannot start a transaction within a transaction" при повторном вызове.
    db.execute(
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
    db.execute("CREATE INDEX IF NOT EXISTS idx_health_metrics_day ON health_metrics(day)")
    db.conn.commit()


def save_health_metrics(
    db_path: Path,
    day: str,
    steps: int | None,
    avg_heart_rate: int | None,
    sleep_hours: float | None,
    stress_level: float | None,
    source: str = "android",
) -> None:
    """Сохраняет метрики здоровья за один день."""
    ensure_health_tables(db_path)
    db = get_reflexio_db(db_path)
    # ПОЧЕМУ: DML (INSERT) оборачивается в transaction() — context manager
    # гарантирует commit при успехе и rollback при любом исключении.
    with db.transaction():
        db.execute(
            """
            INSERT INTO health_metrics
                (day, steps, avg_heart_rate, sleep_hours, stress_level, source, created_at)
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


def list_health_metrics(
    db_path: Path, day_from: str | None = None, day_to: str | None = None
) -> list[dict[str, Any]]:
    """Возвращает список метрик здоровья, опционально фильтруя по диапазону дат."""
    ensure_health_tables(db_path)
    db = get_reflexio_db(db_path)
    # ПОЧЕМУ: db.fetchall() внутри уже вызывает conn.execute().fetchall(),
    # row_factory=sqlite3.Row установлен в get_connection() — dict(r) работает корректно.
    if day_from and day_to:
        rows = db.fetchall(
            "SELECT * FROM health_metrics WHERE day BETWEEN ? AND ? ORDER BY day DESC, id DESC",
            (day_from, day_to),
        )
    elif day_from:
        rows = db.fetchall(
            "SELECT * FROM health_metrics WHERE day = ? ORDER BY id DESC", (day_from,)
        )
    else:
        rows = db.fetchall("SELECT * FROM health_metrics ORDER BY day DESC, id DESC LIMIT 200")

    return [dict(r) for r in rows]
