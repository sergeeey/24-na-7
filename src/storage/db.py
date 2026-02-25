"""
DAL (Data Access Layer) — единый интерфейс для работы с БД.
Поддерживает SQLite и Supabase (PostgreSQL).
"""
import os
import json
from typing import Optional, List, Dict, Any
from pathlib import Path

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("storage.db")
except Exception:
    import logging
    logger = logging.getLogger("storage.db")


# Whitelist разрешённых таблиц для защиты от SQL injection
ALLOWED_TABLES = {
    "transcriptions",
    "ingest_queue",
    "recordings",
    "claims",
    "missions",
    "metrics",
    "audio_meta",
    "text_entries",
    "insights",
    "facts",
    "digests",
    "recording_analyses",
    "_health",  # Служебная таблица Supabase
}


def validate_table_name(table: str) -> None:
    """
    Валидирует имя таблицы против whitelist.
    
    Args:
        table: Имя таблицы для проверки
        
    Raises:
        ValueError: Если имя таблицы не в whitelist
    """
    if table not in ALLOWED_TABLES:
        logger.error("invalid_table_name", table=table, allowed_tables=list(ALLOWED_TABLES))
        raise ValueError(f"Table '{table}' is not in allowed list. Allowed tables: {sorted(ALLOWED_TABLES)}")


class DatabaseBackend:
    """Абстрактный класс для бэкенда БД."""
    
    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Вставляет запись в таблицу."""
        raise NotImplementedError
    
    def select(self, table: str, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Выбирает записи из таблицы."""
        raise NotImplementedError
    
    def update(self, table: str, id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет запись."""
        raise NotImplementedError
    
    def delete(self, table: str, id: str) -> bool:
        """Удаляет запись."""
        raise NotImplementedError


class SQLiteBackend(DatabaseBackend):
    """Бэкенд для SQLite."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        import sqlite3
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
    
    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Вставляет запись в SQLite."""
        # Валидация имени таблицы
        validate_table_name(table)
        
        cursor = self.conn.cursor()
        
        # Конвертируем JSONB в строки для SQLite
        data = data.copy()
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                data[key] = json.dumps(value)
        
        # Валидация имён колонок (защита от SQL injection через имена колонок)
        columns = list(data.keys())
        for col in columns:
            if not col.replace("_", "").isalnum():
                raise ValueError(f"Invalid column name: {col}")
        
        columns_str = ", ".join(columns)
        placeholders = ", ".join(["?" for _ in data])
        values = list(data.values())
        
        cursor.execute(f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})", values)  # nosec B608 — table/columns validated above
        self.conn.commit()
        
        return {"id": data.get("id"), **data}
    
    def select(self, table: str, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Выбирает записи из SQLite."""
        # Валидация имени таблицы
        validate_table_name(table)
        
        cursor = self.conn.cursor()
        
        query = f"SELECT * FROM {table}"  # nosec B608 — table validated by validate_table_name()
        params = []
        
        if filters:
            conditions = []
            for key, value in filters.items():
                # Валидация имени колонки
                if not key.replace("_", "").isalnum():
                    raise ValueError(f"Invalid column name in filter: {key}")
                conditions.append(f"{key} = ?")
                params.append(value)
            query += " WHERE " + " AND ".join(conditions)
        
        if limit:
            if limit < 0:
                raise ValueError("Limit must be non-negative")
            query += f" LIMIT {limit}"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        result = []
        for row in rows:
            row_dict = dict(row)
            # Парсим JSON строки
            for key, value in row_dict.items():
                if isinstance(value, str) and (key.endswith("segments") or key.endswith("urls") or key.endswith("evidence")):
                    try:
                        row_dict[key] = json.loads(value)
                    except Exception:
                        pass
            result.append(row_dict)
        
        return result
    
    def update(self, table: str, id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет запись в SQLite."""
        # Валидация имени таблицы
        validate_table_name(table)
        
        cursor = self.conn.cursor()
        
        # Конвертируем JSONB в строки
        data = data.copy()
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                data[key] = json.dumps(value)
        
        # Валидация имён колонок
        columns = list(data.keys())
        for col in columns:
            if not col.replace("_", "").isalnum():
                raise ValueError(f"Invalid column name: {col}")
        
        set_clause = ", ".join([f"{col} = ?" for col in columns])
        values = list(data.values()) + [id]
        
        cursor.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", values)  # nosec B608 — table/columns validated above
        self.conn.commit()
        
        return data
    
    def delete(self, table: str, id: str) -> bool:
        """Удаляет запись из SQLite."""
        # Валидация имени таблицы
        validate_table_name(table)
        
        cursor = self.conn.cursor()
        cursor.execute(f"DELETE FROM {table} WHERE id = ?", (id,))  # nosec B608 — table validated by validate_table_name()
        self.conn.commit()
        return cursor.rowcount > 0


class SupabaseBackend(DatabaseBackend):
    """Бэкенд для Supabase (PostgreSQL)."""
    
    def __init__(self):
        from src.storage.supabase_client import get_supabase_client
        self.client = get_supabase_client()
        if not self.client:
            raise ValueError("Supabase client not available")
    
    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Вставляет запись в Supabase."""
        # Валидация имени таблицы
        validate_table_name(table)
        
        response = self.client.table(table).insert(data).execute()
        return response.data[0] if response.data else data
    
    def select(self, table: str, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Выбирает записи из Supabase."""
        # Валидация имени таблицы
        validate_table_name(table)
        
        # Валидация имён колонок в фильтрах
        if filters:
            for key in filters.keys():
                if not key.replace("_", "").isalnum():
                    raise ValueError(f"Invalid column name in filter: {key}")
        
        query = self.client.table(table).select("*")
        
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        
        if limit:
            if limit < 0:
                raise ValueError("Limit must be non-negative")
            query = query.limit(limit)
        
        response = query.execute()
        return response.data if response.data else []
    
    def update(self, table: str, id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет запись в Supabase."""
        # Валидация имени таблицы
        validate_table_name(table)
        
        # Валидация имён колонок
        for key in data.keys():
            if not key.replace("_", "").isalnum():
                raise ValueError(f"Invalid column name: {key}")
        
        response = self.client.table(table).update(data).eq("id", id).execute()
        return response.data[0] if response.data else data
    
    def delete(self, table: str, id: str) -> bool:
        """Удаляет запись из Supabase."""
        # Валидация имени таблицы
        validate_table_name(table)
        
        response = self.client.table(table).delete().eq("id", id).execute()
        return len(response.data) > 0 if response.data else False


def get_db() -> DatabaseBackend:
    """
    Фабричная функция для получения бэкенда БД (унифицированный интерфейс).
    
    Returns:
        DatabaseBackend (SQLite или Supabase)
    """
    return get_db_backend()


def get_db_backend() -> DatabaseBackend:
    """
    Фабричная функция для получения бэкенда БД.
    
    Returns:
        DatabaseBackend (SQLite или Supabase)
    """
    from src.utils.config import settings
    
    backend = os.getenv("DB_BACKEND", getattr(settings, "DB_BACKEND", "sqlite"))
    
    if backend == "supabase":
        try:
            return SupabaseBackend()
        except Exception as e:
            logger.warning("supabase_backend_failed", error=str(e), fallback="sqlite")
            backend = "sqlite"
    
    if backend == "sqlite":
        db_path = settings.STORAGE_PATH / "reflexio.db"
        return SQLiteBackend(db_path)
    
    raise ValueError(f"Unknown backend: {backend}")


# Функция get_db_backend уже определена выше, не переопределяем


# Async версии (для будущего использования)
try:
    import asyncio  # noqa: F401
    import asyncpg  # noqa: F401
    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False


async def get_async_db_backend():
    """Async версия для PostgreSQL (опционально)."""
    if not HAS_ASYNC:
        raise ImportError("asyncpg not installed")
    
    # Реализация для async PostgreSQL
    pass

