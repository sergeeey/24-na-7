"""
DAL (Data Access Layer) — единый интерфейс для работы с БД.
Поддерживает SQLite и Supabase (PostgreSQL).
"""
import os
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("storage.db")
except Exception:
    import logging
    logger = logging.getLogger("storage.db")


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
        cursor = self.conn.cursor()
        
        # Конвертируем JSONB в строки для SQLite
        data = data.copy()
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                data[key] = json.dumps(value)
        
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        values = list(data.values())
        
        cursor.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)
        self.conn.commit()
        
        return {"id": data.get("id"), **data}
    
    def select(self, table: str, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Выбирает записи из SQLite."""
        cursor = self.conn.cursor()
        
        query = f"SELECT * FROM {table}"
        params = []
        
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(f"{key} = ?")
                params.append(value)
            query += " WHERE " + " AND ".join(conditions)
        
        if limit:
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
                    except:
                        pass
            result.append(row_dict)
        
        return result
    
    def update(self, table: str, id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет запись в SQLite."""
        cursor = self.conn.cursor()
        
        # Конвертируем JSONB в строки
        data = data.copy()
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                data[key] = json.dumps(value)
        
        set_clause = ", ".join([f"{key} = ?" for key in data.keys()])
        values = list(data.values()) + [id]
        
        cursor.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", values)
        self.conn.commit()
        
        return data
    
    def delete(self, table: str, id: str) -> bool:
        """Удаляет запись из SQLite."""
        cursor = self.conn.cursor()
        cursor.execute(f"DELETE FROM {table} WHERE id = ?", (id,))
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
        response = self.client.table(table).insert(data).execute()
        return response.data[0] if response.data else data
    
    def select(self, table: str, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Выбирает записи из Supabase."""
        query = self.client.table(table).select("*")
        
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        
        if limit:
            query = query.limit(limit)
        
        response = query.execute()
        return response.data if response.data else []
    
    def update(self, table: str, id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет запись в Supabase."""
        response = self.client.table(table).update(data).eq("id", id).execute()
        return response.data[0] if response.data else data
    
    def delete(self, table: str, id: str) -> bool:
        """Удаляет запись из Supabase."""
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
    import asyncio
    import asyncpg
    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False


async def get_async_db_backend():
    """Async версия для PostgreSQL (опционально)."""
    if not HAS_ASYNC:
        raise ImportError("asyncpg not installed")
    
    # Реализация для async PostgreSQL
    pass

