"""
DAL (Data Access Layer) — единый интерфейс для работы с БД.
Поддерживает SQLite и Supabase (PostgreSQL).
"""
import os
import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Union, Generator

# ПОЧЕМУ graceful import: sqlcipher3 требует нативной libsqlcipher-dev.
# На dev-машинах без неё — fallback на plain sqlite3 с предупреждением.
# В production (VPS) — sqlcipher3 установлен → шифрование активно.
try:
    import sqlcipher3 as _sqlcipher_module
    _SQLCIPHER_AVAILABLE = True
except ImportError:
    _sqlcipher_module = None  # type: ignore[assignment]
    _SQLCIPHER_AVAILABLE = False
from pathlib import Path

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("storage.db")
except Exception:
    import logging
    logger = logging.getLogger("storage.db")


# ──────────────────────────────────────────────
# Connection Factory — единая точка создания SQLite connections
# ПОЧЕМУ: 31 файл делал sqlite3.connect() без pragmas.
# WAL mode + busy_timeout + cache — базовый минимум для concurrent access.
# ──────────────────────────────────────────────

def get_connection(db_path: Union[str, Path], *, check_same_thread: bool = False) -> sqlite3.Connection:
    """
    Создаёт SQLite connection с production-grade pragmas.

    Args:
        db_path: путь к файлу БД
        check_same_thread: по умолчанию False для FastAPI (multi-thread).
            Потокобезопасность обеспечивается на уровне приложения.

    Returns:
        sqlite3.Connection с настроенными pragmas и row_factory
    """
    # ПОЧЕМУ isolation_level=None: autocommit mode. Python sqlite3 default ("")
    # магически управляет транзакциями, что вызывает "ghost transactions"
    # после SELECT — данные невидимы между singleton connections в тестах.
    # С None — каждый statement auto-commits, а транзакции начинаем явно через BEGIN.
    sqlcipher_key = os.environ.get("SQLCIPHER_KEY", "")
    if not sqlcipher_key:
        # ПОЧЕМУ файловый fallback: docker restart не перечитывает .env,
        # только docker compose up. Файл монтируется через ./src volume —
        # доступен сразу без пересоздания контейнера.
        _key_file = Path(__file__).parent / ".sqlcipher_key"
        if _key_file.exists():
            sqlcipher_key = _key_file.read_text(encoding="utf-8").strip()
    if _SQLCIPHER_AVAILABLE and sqlcipher_key:
        # ПОЧЕМУ sqlcipher3 вместо sqlite3: AES-256-CBC шифрование всего файла БД.
        # Без ключа — бинарный мусор. Блокер для App Store.
        # key задаётся PRAGMA key СРАЗУ после connect — до любого другого запроса.
        conn = _sqlcipher_module.connect(str(db_path), check_same_thread=check_same_thread, isolation_level=None)
        conn.row_factory = _sqlcipher_module.Row
        conn.execute(f"PRAGMA key = \"{sqlcipher_key}\"")  # nosec B608 — key from env, not user input
    else:
        if sqlcipher_key and not _SQLCIPHER_AVAILABLE:
            logger.warning("sqlcipher_unavailable", reason="sqlcipher3 not installed, falling back to plain sqlite3")
        conn = sqlite3.connect(str(db_path), check_same_thread=check_same_thread, isolation_level=None)
        conn.row_factory = sqlite3.Row

    # ПОЧЕМУ каждый pragma:
    # WAL — читатели не блокируют писателей (критично для concurrent WebSocket)
    # synchronous=NORMAL — баланс скорость/надёжность (FULL слишком медленный для WAL)
    # busy_timeout=5000 — ждать 5 сек вместо мгновенного SQLITE_BUSY
    # cache_size=-65536 — 64MB page cache (дефолт 2MB, наши данные больше)
    # mmap_size=268435456 — 256MB memory-mapped I/O для read-heavy workload
    # temp_store=MEMORY — temp таблицы в RAM (не на диск)
    # foreign_keys=ON — SQLite по дефолту не проверяет FK, это баг-магнит
    # wal_autocheckpoint=1000 — checkpoint каждые 1000 страниц (дефолт)
    pragmas = [
        ("journal_mode", "WAL"),
        ("synchronous", "NORMAL"),
        ("busy_timeout", "5000"),
        ("cache_size", "-65536"),
        ("mmap_size", "268435456"),
        ("temp_store", "MEMORY"),
        ("foreign_keys", "ON"),
        ("wal_autocheckpoint", "1000"),
    ]

    cursor = conn.cursor()
    for pragma_name, pragma_value in pragmas:
        cursor.execute(f"PRAGMA {pragma_name} = {pragma_value}")  # nosec B608 — hardcoded values, not user input

    # Верифицируем WAL (journal_mode SET возвращает результат)
    result = cursor.execute("PRAGMA journal_mode").fetchone()
    actual_mode = result[0] if result else "unknown"
    if actual_mode != "wal":
        logger.warning("wal_mode_not_set", expected="wal", actual=actual_mode, db_path=str(db_path))

    cursor.close()
    return conn


# ──────────────────────────────────────────────
# ReflexioDB — gateway для всех модулей
# ПОЧЕМУ: 17 файлов делают sqlite3.connect() каждый по-своему.
# ReflexioDB — singleton per db_path, thread-local connections,
# WAL pragmas на каждом connection, transaction() context manager.
# Потоки получают свой connection (SQLite не thread-safe per connection),
# но все через одну точку с гарантированными настройками.
# ──────────────────────────────────────────────

class ReflexioDB:
    """
    Thread-safe SQLite gateway с WAL mode.

    Singleton per db_path. Каждый поток получает свой connection
    через threading.local(). Все connections создаются через
    get_connection() с production pragmas.
    """

    _instances: Dict[str, "ReflexioDB"] = {}
    _instances_lock = threading.Lock()

    def __init__(self, db_path: Union[str, Path]) -> None:
        self.db_path = str(db_path)
        self._local = threading.local()

    @classmethod
    def get_instance(cls, db_path: Union[str, Path]) -> "ReflexioDB":
        """Singleton per db_path — один gateway на файл БД."""
        key = str(db_path)
        if key not in cls._instances:
            with cls._instances_lock:
                if key not in cls._instances:
                    cls._instances[key] = cls(db_path)
                    logger.info("reflexio_db_created", db_path=key)
        return cls._instances[key]

    @property
    def conn(self) -> sqlite3.Connection:
        """Thread-local connection (создаётся лениво)."""
        c = getattr(self._local, "conn", None)
        if c is None:
            c = get_connection(self.db_path)
            self._local.conn = c
        return c

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Выполняет SQL и возвращает cursor."""
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params_seq: list) -> sqlite3.Cursor:
        """Выполняет SQL для каждого набора параметров."""
        return self.conn.executemany(sql, params_seq)

    def executescript(self, sql: str) -> sqlite3.Cursor:
        """Выполняет SQL-скрипт (несколько statements)."""
        return self.conn.executescript(sql)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Выполняет SELECT и возвращает одну строку."""
        return self.conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Выполняет SELECT и возвращает все строки."""
        return self.conn.execute(sql, params).fetchall()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager для транзакций: commit при успехе, rollback при ошибке.

        Usage:
            with db.transaction() as conn:
                conn.execute("INSERT ...", (...))
                conn.execute("UPDATE ...", (...))
            # auto-commit
        """
        conn = self.conn
        conn.execute("BEGIN")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close_thread_connection(self) -> None:
        """Закрывает connection текущего потока."""
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None


def ensure_all_tables(db_path: Union[str, Path]) -> None:
    """
    Создаёт все необходимые таблицы одним вызовом.

    ПОЧЕМУ lazy imports: db.py импортируется всеми модулями.
    Прямой import создаёт circular dependency. Lazy — только при вызове
    (один раз на startup), нет overhead.
    """
    from src.storage.ingest_persist import ensure_ingest_tables
    from src.storage.integrity import ensure_integrity_tables
    from src.memory.semantic_memory import ensure_semantic_memory_tables
    from src.balance.storage import ensure_balance_tables
    from src.storage.health_metrics import ensure_health_tables
    from src.persongraph.service import ensure_person_graph_tables

    path = Path(db_path)
    ensure_ingest_tables(path)
    ensure_integrity_tables(path)
    ensure_semantic_memory_tables(path)
    ensure_balance_tables(path)
    ensure_health_tables(path)
    ensure_person_graph_tables(path)
    logger.info("all_tables_ensured", db_path=str(path))


def run_migrations(db_path: Union[str, Path]) -> list[str]:
    """
    Применяет SQLite миграции из src/storage/migrations/sqlite/.

    ПОЧЕМУ отдельный каталог sqlite/: существующие 0001-0009 — PostgreSQL/Supabase.
    SQLite миграции начинаются с 0010 и содержат только SQLite-совместимый DDL.

    Returns:
        Список имён применённых миграций.
    """
    import hashlib
    from datetime import datetime, timezone

    db = get_reflexio_db(db_path)

    # Создаём таблицу tracking (DDL — без transaction)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            checksum TEXT NOT NULL
        )
        """
    )
    db.conn.commit()

    # Ищем SQL файлы
    migrations_dir = Path(__file__).parent / "migrations" / "sqlite"
    if not migrations_dir.exists():
        return []

    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        return []

    # Какие уже применены
    applied = {
        row["name"]
        for row in db.fetchall("SELECT name FROM schema_migrations")
    }

    applied_now: list[str] = []
    for sql_file in sql_files:
        name = sql_file.name
        if name in applied:
            continue

        content = sql_file.read_text(encoding="utf-8")
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16]

        try:
            # ПОЧЕМУ executescript: миграция может содержать несколько statements.
            # executescript автоматически коммитит после каждого statement.
            db.conn.executescript(content)
            with db.transaction():
                db.execute(
                    "INSERT INTO schema_migrations (name, applied_at, checksum) VALUES (?, ?, ?)",
                    (name, datetime.now(timezone.utc).isoformat(), checksum),
                )
            applied_now.append(name)
            logger.info("migration_applied", name=name, checksum=checksum)
        except Exception as e:
            logger.error("migration_failed", name=name, error=str(e))
            raise

    return applied_now


def get_reflexio_db(db_path: Optional[Union[str, Path]] = None) -> ReflexioDB:
    """
    Фабричная функция — основной способ получить ReflexioDB.

    Если db_path не указан, берёт из settings.STORAGE_PATH.
    """
    if db_path is None:
        from src.utils.config import settings
        db_path = settings.STORAGE_PATH / "reflexio.db"
    return ReflexioDB.get_instance(db_path)


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
    "_health",          # Служебная таблица Supabase
    # Social graph (migration 0009)
    "persons",
    "person_voice_samples",
    "person_voice_profiles",   # профили окружения (voice_profiles = профиль пользователя)
    "person_interactions",
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
        self.conn = get_connection(db_path)
    
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

