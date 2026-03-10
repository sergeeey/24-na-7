"""DI-зависимости для FastAPI-роутеров Reflexio 24/7.

Цель модуля — централизовать создание общих зависимостей:
- доступ к настройкам (`Settings`);
- доступ к базе данных (`ReflexioDB`).

Роутеры могут использовать эти функции через FastAPI `Depends`,
что упрощает тестирование (подмена зависимостей) и будущую
миграцию хранилища (например, на Supabase/PostgreSQL).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from src.storage.db import ReflexioDB, get_reflexio_db
from src.utils.config import Settings, settings


@lru_cache
def get_settings() -> Settings:
    """Возвращает singleton Settings.

    ПОЧЕМУ lru_cache: Settings читают .env и окружение; делать это один раз.
    """
    return settings


def _get_db_path(cfg: Settings) -> Path:
    return cfg.STORAGE_PATH / "reflexio.db"


def get_db(cfg: Annotated[Settings, Depends(get_settings)]) -> ReflexioDB:
    """Возвращает подключение к основной БД Reflexio.

    Сейчас это локальный SQLite/SQLCipher файл `reflexio.db`.
    В будущем реализацию можно заменить на Supabase/PostgreSQL,
    не меняя сигнатуры зависимостей в роутерах.
    """
    db_path = _get_db_path(cfg)
    return get_reflexio_db(db_path)

