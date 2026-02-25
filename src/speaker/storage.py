"""SQLite операции для speaker verification: профили и миграция схемы.

Таблицы:
- voice_profiles: усреднённый голосовой профиль пользователя (embedding)
- transcriptions: добавляем speaker_id, is_user, speaker_confidence (ALTER TABLE)
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from src.utils.logging import get_logger

logger = get_logger("speaker.storage")


def ensure_speaker_tables(db_path: Path) -> None:
    """Создаёт/обновляет таблицы для speaker verification.

    ПОЧЕМУ ALTER TABLE с try/except:
        SQLite не поддерживает ADD COLUMN IF NOT EXISTS.
        OperationalError с "duplicate column name" = столбец уже есть — игнорируем.
        Это safe idempotent миграция (можно вызывать многократно).
    """
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        # 1. Таблица голосовых профилей
        conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_profiles (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default',
                embedding_json TEXT NOT NULL,
                sample_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TEXT
            )
        """)

        # 2. Добавляем столбцы к transcriptions (safe ALTER TABLE)
        # ПОЧЕМУ DEFAULT 1 для is_user: backward-compatible — старые записи считаются
        # пользовательскими (до включения верификации всё было от пользователя).
        speaker_columns = [
            ("speaker_id", "INTEGER DEFAULT 0"),
            ("is_user", "BOOLEAN DEFAULT 1"),
            ("speaker_confidence", "REAL DEFAULT 0.0"),
        ]
        for col_name, col_def in speaker_columns:
            try:
                conn.execute(
                    f"ALTER TABLE transcriptions ADD COLUMN {col_name} {col_def}"
                )
                logger.info("speaker_column_added", column=col_name)
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    pass  # Уже существует — ок
                else:
                    logger.warning("alter_table_failed", column=col_name, error=str(e))

        conn.commit()
        logger.info("speaker_tables_ready", db=str(db_path))
    finally:
        conn.close()


def save_voice_profile(
    db_path: Path,
    embedding: np.ndarray,
    user_id: str = "default",
    sample_count: int = 1,
) -> str:
    """Сохраняет голосовой профиль в БД. Деактивирует предыдущий профиль.

    Returns:
        profile_id — UUID новой записи
    """
    ensure_speaker_tables(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        profile_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Деактивируем старый профиль
        conn.execute(
            "UPDATE voice_profiles SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )

        conn.execute(
            """
            INSERT INTO voice_profiles (id, user_id, embedding_json, sample_count, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (profile_id, user_id, json.dumps(embedding.tolist()), sample_count, now),
        )
        conn.commit()
        logger.info("voice_profile_saved", profile_id=profile_id, user_id=user_id, samples=sample_count)
        return profile_id
    finally:
        conn.close()


def load_active_profile_embedding(
    db_path: Path, user_id: str = "default"
) -> Optional[np.ndarray]:
    """Загружает активный embedding из БД.

    Returns:
        np.ndarray(256,) float32 или None если профиль не создан
    """
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT embedding_json FROM voice_profiles
            WHERE user_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return np.array(json.loads(row[0]), dtype=np.float32)
    except Exception as e:
        logger.warning("load_profile_failed", user_id=user_id, error=str(e))
        return None
    finally:
        conn.close()


def has_active_profile(db_path: Path, user_id: str = "default") -> bool:
    """Проверяет, есть ли активный профиль у пользователя."""
    return load_active_profile_embedding(db_path, user_id) is not None
