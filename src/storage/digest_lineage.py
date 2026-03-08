"""
Digest Data Lineage — связь дайджестов с исходными транскрипциями.

ПОЧЕМУ нужно: дайджест сейчас чёрный ящик. Пользователь не может проверить
откуда взялся инсайт "ты говорил о стрессе 5 раз". digest_sources даёт:
  1. Прозрачность: GET /digest/{date}/sources → список оригинальных записей
  2. GDPR: при удалении пользователя → cascade delete дайджестов по lineage
  3. Debugging: почему дайджест пустой? — смотри sources, сколько транскрипций

Архитектура: fire-and-forget, как event_log. Ошибка записи lineage
не ломает дайджест — он уже сгенерирован и закеширован.
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.utils.logging import get_logger

logger = get_logger("storage.digest_lineage")


def ensure_digest_sources_table(db: Any) -> None:
    """Создаёт таблицу digest_sources (идемпотентно)."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS digest_sources (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT    NOT NULL,
            transcription_id TEXT   NOT NULL,
            ingest_id        TEXT,
            created_at       TEXT   DEFAULT (datetime('now'))
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_digest_sources_date ON digest_sources(date)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_digest_sources_uniq "
        "ON digest_sources(date, transcription_id)"
    )
    db.conn.commit()


def save_digest_sources(date: str, transcriptions: List[Dict[str, Any]]) -> None:
    """
    Сохраняет lineage: какие транскрипции участвовали в дайджесте за date.

    ПОЧЕМУ INSERT OR IGNORE: при force-regeneration дайджест пересчитывается,
    но источники те же — не дублируем строки.

    Args:
        date: YYYY-MM-DD
        transcriptions: список dict с ключами 'id' (transcription_id) и 'ingest_id'
    """
    if not transcriptions:
        return
    try:
        from src.storage.db import get_reflexio_db
        db = get_reflexio_db()
        ensure_digest_sources_table(db)
        rows = [
            (date, t.get("id", ""), t.get("ingest_id"))
            for t in transcriptions
            if t.get("id")
        ]
        if not rows:
            return
        db.conn.executemany(
            "INSERT OR IGNORE INTO digest_sources (date, transcription_id, ingest_id) VALUES (?, ?, ?)",
            rows,
        )
        db.conn.commit()
        logger.info("digest_sources_saved", date=date, count=len(rows))
    except Exception as e:
        logger.warning("digest_sources_save_failed", date=date, error=str(e))


def get_digest_sources(date: str) -> Dict[str, Any]:
    """
    Возвращает все транскрипции-источники для дайджеста за date.

    Returns:
        {
          "date": "2026-03-03",
          "count": 47,
          "sources": [{"transcription_id": "...", "ingest_id": "...", "created_at": "..."}, ...]
        }
    """
    try:
        from src.storage.db import get_reflexio_db
        db = get_reflexio_db()
        rows = db.fetchall(
            """
            SELECT ds.transcription_id, ds.ingest_id, ds.created_at,
                   t.text, t.language, t.created_at as transcription_created_at
            FROM digest_sources ds
            LEFT JOIN transcriptions t ON t.id = ds.transcription_id
            WHERE ds.date = ?
            ORDER BY ds.id
            """,
            (date,),
        )
        sources = [
            {
                "transcription_id": row[0],
                "ingest_id": row[1],
                "linked_at": row[2],
                "text_preview": (row[3] or "")[:100] if row[3] else None,
                "language": row[4],
                "transcription_at": row[5],
            }
            for row in rows
        ]
        return {"date": date, "count": len(sources), "sources": sources}
    except Exception as e:
        logger.warning("digest_sources_get_failed", date=date, error=str(e))
        return {"date": date, "count": 0, "sources": []}
