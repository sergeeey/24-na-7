"""
Векторный поиск по structured_events через sqlite-vec.

ПОЧЕМУ sqlite-vec, а не ChromaDB/FAISS:
  1 pip install, нет отдельного процесса, работает с SQLCipher через load_extension.
  Cosine similarity в SQL, а не O(N) Python-цикл.

Архитектура:
  vec_events (virtual table) — embedding float[384] для каждого structured_event.
  Запись: index_event() вызывается при persist нового события.
  Чтение: search_events() → SQL MATCH → ids → JOIN structured_events.
"""
from __future__ import annotations

import struct
from typing import Any, List

from src.utils.logging import get_logger

logger = get_logger("storage.vec_search")

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 / hash_fallback
_VEC_AVAILABLE: bool | None = None  # None = не проверяли


def _is_available() -> bool:
    """Кешированная проверка доступности sqlite_vec."""
    global _VEC_AVAILABLE
    if _VEC_AVAILABLE is not None:
        return _VEC_AVAILABLE
    try:
        import sqlite_vec  # noqa: F401
        _VEC_AVAILABLE = True
    except ImportError:
        _VEC_AVAILABLE = False
        logger.warning("sqlite_vec_unavailable", reason="pip install sqlite-vec")
    return _VEC_AVAILABLE


def load_vec_extension(conn: Any) -> bool:
    """
    Загружает sqlite-vec extension в connection.

    ПОЧЕМУ enable_load_extension(True/False): Python sqlite3/sqlcipher3
    запрещает load_extension по умолчанию (безопасность). Открываем только
    на время загрузки и сразу закрываем.

    Returns:
        True если extension загружено, False при ошибке.
    """
    if not _is_available():
        return False
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except Exception as e:
        logger.warning("vec_extension_load_failed", error=str(e))
        return False


def ensure_vec_table(conn: Any) -> bool:
    """
    Создаёт виртуальную таблицу vec_events (идемпотентно).

    ПОЧЕМУ vec0, а не другие типы: vec0 поддерживает KNN (k-nearest-neighbour)
    через MATCH оператор с автоматическим косинусным расстоянием для float[].
    """
    if not load_vec_extension(conn):
        return False
    try:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_events "
            f"USING vec0(event_rowid INTEGER PRIMARY KEY, embedding float[{EMBEDDING_DIM}])"
        )
        conn.commit()
        return True
    except Exception as e:
        logger.warning("vec_table_create_failed", error=str(e))
        return False


def _to_blob(vector: List[float]) -> bytes:
    """Конвертирует list[float] → binary blob (little-endian float32)."""
    dim = len(vector)
    if dim < EMBEDDING_DIM:
        vector = vector + [0.0] * (EMBEDDING_DIM - dim)
    elif dim > EMBEDDING_DIM:
        vector = vector[:EMBEDDING_DIM]
    return struct.pack(f"{EMBEDDING_DIM}f", *vector)


def index_event(conn: Any, event_id: str, text: str) -> bool:
    """
    Индексирует одно событие: генерирует embedding → сохраняет в vec_events.

    ПОЧЕМУ rowid через structured_events.rowid:
    vec0 требует INTEGER PRIMARY KEY (rowid), а не TEXT UUID.
    Маппинг event_id → rowid делаем через SELECT rowid FROM structured_events.
    """
    if not text or not text.strip():
        return False
    try:
        from src.storage.embeddings import generate_embeddings
        row = conn.execute(
            "SELECT rowid FROM structured_events WHERE id = ?", (event_id,)
        ).fetchone()
        if not row:
            return False
        rowid = row[0]

        embedding = generate_embeddings(text)
        blob = _to_blob(embedding)

        # INSERT OR REPLACE — идемпотентно при переиндексации
        conn.execute(
            "INSERT OR REPLACE INTO vec_events(event_rowid, embedding) VALUES (?, ?)",
            (rowid, blob),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.warning("vec_index_event_failed", id=id, error=str(e))
        return False


def search_events(conn: Any, query: str, limit: int = 10) -> List[dict]:
    """
    Семантический поиск событий по cosine similarity.

    Returns:
        List[{id, text, distance, topics, emotions, created_at}]
        Отсортировано по distance (меньше = ближе).
    """
    if not query.strip():
        return []
    if not load_vec_extension(conn):
        return []

    try:
        from src.storage.embeddings import generate_embeddings
        query_blob = _to_blob(generate_embeddings(query))

        rows = conn.execute(
            """
            SELECT
                se.id,
                se.text,
                se.topics,
                se.emotions,
                se.created_at,
                v.distance
            FROM vec_events v
            JOIN structured_events se ON se.rowid = v.event_rowid
            WHERE v.embedding MATCH ?
              AND k = ?
              AND se.is_current = 1
            ORDER BY v.distance
            """,
            (query_blob, limit),
        ).fetchall()

        results = []
        for row in rows:
            import json
            topics = row[2] or "[]"
            emotions = row[3] or "[]"
            try:
                topics = json.loads(topics) if isinstance(topics, str) else topics
                emotions = json.loads(emotions) if isinstance(emotions, str) else emotions
            except Exception:
                pass
            results.append({
                "id": row[0],
                "text": row[1],
                "topics": topics,
                "emotions": emotions,
                "created_at": row[4],
                "distance": round(row[5], 4),
            })
        return results
    except Exception as e:
        logger.error("vec_search_failed", error=str(e))
        return []


def retroindex_all(conn: Any) -> int:
    """
    Индексирует все structured_events которые ещё не в vec_events.

    Запускается один раз при деплое или через /admin/reindex endpoint.
    Returns: количество проиндексированных событий.
    """
    if not ensure_vec_table(conn):
        return 0

    try:
        # Только события без индекса
        rows = conn.execute(
            """
            SELECT se.id, se.text, se.rowid
            FROM structured_events se
            LEFT JOIN vec_events v ON v.event_rowid = se.rowid
            WHERE se.is_current = 1
              AND se.text IS NOT NULL
              AND se.text != ''
              AND v.event_rowid IS NULL
            """
        ).fetchall()

        if not rows:
            logger.info("retroindex_nothing_to_do")
            return 0

        from src.storage.embeddings import generate_embeddings
        count = 0
        for id, text, rowid in rows:
            try:
                embedding = generate_embeddings(text)
                blob = _to_blob(embedding)
                conn.execute(
                    "INSERT OR REPLACE INTO vec_events(event_rowid, embedding) VALUES (?, ?)",
                    (rowid, blob),
                )
                count += 1
                if count % 100 == 0:
                    conn.commit()
                    logger.info("retroindex_progress", count=count, total=len(rows))
            except Exception as e:
                logger.warning("retroindex_event_failed", id=id, error=str(e))

        conn.commit()
        logger.info("retroindex_complete", indexed=count, total=len(rows))
        return count
    except Exception as e:
        logger.error("retroindex_failed", error=str(e))
        return 0
