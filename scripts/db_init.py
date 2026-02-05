"""
Инициализация базы данных Reflexio 24/7.

Загружает схему SQL и создаёт необходимые таблицы.
"""
import sys
import sqlite3
from pathlib import Path

from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("db_init")


def init_database(schema_path: Path | str) -> None:
    """
    Инициализирует базу данных из SQL-схемы.
    
    Args:
        schema_path: Путь к файлу schema.sql
    """
    schema_path = Path(schema_path)
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    # Определяем путь к БД
    db_path = settings.STORAGE_PATH / "reflexio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info("initializing_database", db_path=str(db_path), schema=str(schema_path))
    
    # Загружаем схему
    schema_sql = schema_path.read_text(encoding="utf-8")
    
    # Подключаемся к БД и выполняем схему
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.executescript(schema_sql)
        conn.commit()
        
        # Проверяем созданные таблицы
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        logger.info("database_initialized", tables=tables, db_path=str(db_path))
        print(f"✅ Database initialized: {db_path}")
        print(f"   Tables: {', '.join(tables)}")
    except sqlite3.Error as e:
        logger.error("database_init_failed", error=str(e))
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    """Точка входа для скрипта."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/db_init.py <schema.sql>")
        sys.exit(1)
    
    schema_file = sys.argv[1]
    
    try:
        init_database(schema_file)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()













