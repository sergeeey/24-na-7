"""DI-зависимости для FastAPI-роутеров Reflexio 24/7.

Цель модуля — централизовать создание общих зависимостей:
- доступ к настройкам (`Settings`);
- доступ к базе данных (`ReflexioDB`).
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
    """Возвращает singleton Settings."""
    return settings


def _get_db_path(cfg: Settings) -> Path:
    return cfg.STORAGE_PATH / "reflexio.db"


def get_db(cfg: Annotated[Settings, Depends(get_settings)]) -> ReflexioDB:
    """Возвращает подключение к основной БД Reflexio."""
    return get_reflexio_db(_get_db_path(cfg))
