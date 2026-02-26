"""Minimal personal graph persistence and insight synthesis."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.psychology.liwc_markers import analyze_linguistic_markers


def ensure_person_graph_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS person_graph_events (
                id TEXT PRIMARY KEY,
                day TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_person_graph_day ON person_graph_events(day)")
        conn.commit()
    finally:
        conn.close()


def save_day_psychology_snapshot(db_path: Path, day: str, text: str) -> dict[str, Any]:
    ensure_person_graph_tables(db_path)
    markers = analyze_linguistic_markers(text)
    payload = {
        "markers": markers,
        "summary": _build_simple_summary(markers),
    }
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO person_graph_events (id, day, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                day,
                "psychology_snapshot",
                json.dumps(payload, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return payload


def get_day_insights(db_path: Path, day: str) -> list[dict[str, str]]:
    ensure_person_graph_tables(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT payload_json FROM person_graph_events WHERE day = ? AND event_type='psychology_snapshot' ORDER BY created_at DESC LIMIT 1",
            (day,),
        ).fetchone()
        if not row:
            return []
        payload = json.loads(row["payload_json"] or "{}")
        summary = payload.get("summary", "")

        return [
            {"role": "psychologist", "insight": summary or "Явных маркеров не найдено."},
            {"role": "coach", "insight": "Сформулируй 1 измеримую задачу с дедлайном на завтра."},
            {"role": "pattern_detector", "insight": "Отслеживай повтор слов 'должен/потом' как триггеры напряжения."},
            {"role": "devil_advocate", "insight": "Проверь, где избегание маскируется под 'нет времени'."},
            {"role": "future_predictor", "insight": "Если паттерн сохранится 7 дней, риск выгорания повышается."},
        ]
    finally:
        conn.close()


def _build_simple_summary(markers: dict[str, Any]) -> str:
    abs_score = markers.get("absolutism_score", 0.0)
    self_score = markers.get("self_criticism_score", 0.0)
    proc_score = markers.get("procrastination_score", 0.0)

    parts = []
    if abs_score > 0.01:
        parts.append("заметны признаки категоричности")
    if self_score > 0.01:
        parts.append("есть маркеры самокритики")
    if proc_score > 0.01:
        parts.append("есть сигналы откладывания")
    if not parts:
        return "Речь нейтральна, выраженных когнитивных искажений не видно."
    return "В речи " + ", ".join(parts) + "."
