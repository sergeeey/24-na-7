"""Minimal personal graph persistence and insight synthesis."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.psychology.liwc_markers import analyze_linguistic_markers
from src.storage.db import get_reflexio_db


def ensure_person_graph_tables(db_path: Path) -> None:
    """Создаёт таблицы person_graph_events и индексы если их нет."""
    # ПОЧЕМУ: mkdir здесь, а не в get_reflexio_db — сервис сам отвечает за
    # то, что его директория существует до открытия соединения.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)

    # ПОЧЕМУ без transaction(): DDL в SQLite неявно auto-commit; обёртка
    # transaction() здесь не нужна и может конфликтовать с WAL checkpoint.
    db.execute(
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
    db.execute("CREATE INDEX IF NOT EXISTS idx_person_graph_day ON person_graph_events(day)")
    db.conn.commit()


def save_day_psychology_snapshot(db_path: Path, day: str, text: str) -> dict[str, Any]:
    """
    Анализирует текст дня, сохраняет snapshot в БД и возвращает payload.

    Args:
        db_path: Путь к файлу SQLite.
        day: Дата в формате YYYY-MM-DD.
        text: Транскрипт дня для анализа.

    Returns:
        Словарь с markers и summary.
    """
    ensure_person_graph_tables(db_path)
    markers = analyze_linguistic_markers(text)
    payload = {
        "markers": markers,
        "summary": _build_simple_summary(markers),
    }
    db = get_reflexio_db(db_path)

    # ПОЧЕМУ transaction(): INSERT — DML, нужна гарантия атомарности и
    # rollback при ошибке. transaction() делает commit/rollback автоматически.
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO person_graph_events (id, day, event_type, payload_json, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                day,
                "psychology_snapshot",
                json.dumps(payload, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return payload


def get_day_insights(db_path: Path, day: str) -> list[dict[str, str]]:
    """
    Возвращает список инсайтов для указанного дня.

    Args:
        db_path: Путь к файлу SQLite.
        day: Дата в формате YYYY-MM-DD.

    Returns:
        Список словарей {role, insight} или пустой список.
    """
    ensure_person_graph_tables(db_path)
    db = get_reflexio_db(db_path)

    # ПОЧЕМУ db.fetchone(): метод уже инкапсулирует execute + fetchone,
    # row_factory=sqlite3.Row настроен внутри get_connection() — row["col"] работает.
    row = db.fetchone(
        "SELECT payload_json FROM person_graph_events"
        " WHERE day = ? AND event_type='psychology_snapshot'"
        " ORDER BY created_at DESC LIMIT 1",
        (day,),
    )
    if not row:
        return []
    payload = json.loads(row["payload_json"] or "{}")
    summary = payload.get("summary", "")

    return [
        {"role": "psychologist", "insight": summary or "Явных маркеров не найдено."},
        {"role": "coach", "insight": "Сформулируй 1 измеримую задачу с дедлайном на завтра."},
        {
            "role": "pattern_detector",
            "insight": "Отслеживай повтор слов 'должен/потом' как триггеры напряжения.",
        },
        {
            "role": "devil_advocate",
            "insight": "Проверь, где избегание маскируется под 'нет времени'.",
        },
        {
            "role": "future_predictor",
            "insight": "Если паттерн сохранится 7 дней, риск выгорания повышается.",
        },
    ]


def _build_simple_summary(markers: dict[str, Any]) -> str:
    """Строит текстовый вывод по числовым маркерам LIWC."""
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
