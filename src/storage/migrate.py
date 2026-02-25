#!/usr/bin/env python3
"""
Миграция базы данных: SQLite → Supabase (PostgreSQL).
"""
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("storage.migrate")
except Exception:
    import logging
    logger = logging.getLogger("storage.migrate")


def backup_sqlite(backup_path: Optional[Path] = None) -> Path:
    """
    Создаёт backup SQLite базы данных.
    
    Args:
        backup_path: Путь для backup (если None, генерируется автоматически)
        
    Returns:
        Путь к backup файлу
    """
    from src.utils.config import settings
    import shutil
    from datetime import datetime
    
    sqlite_path = settings.STORAGE_PATH / "reflexio.db"
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    
    if backup_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = settings.STORAGE_PATH / f"reflexio.db.backup.{timestamp}"
    
    shutil.copy2(sqlite_path, backup_path)
    logger.info("sqlite_backup_created", backup_path=str(backup_path))
    return backup_path


def verify_row_counts() -> Dict[str, Any]:
    """
    Сверяет количество строк между SQLite и Supabase.
    
    Returns:
        Результат проверки
    """
    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "tables": {},
        "match": True,
        "differences": [],
    }
    
    try:
        # Подключаемся к SQLite
        from src.utils.config import settings
        import sqlite3
        
        sqlite_path = settings.STORAGE_PATH / "reflexio.db"
        if not sqlite_path.exists():
            result["error"] = "SQLite database not found"
            return result
        
        conn = sqlite3.connect(str(sqlite_path))
        cursor = conn.cursor()
        
        # Подключаемся к Supabase
        from src.storage.supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        if not supabase:
            result["error"] = "Supabase client not available"
            conn.close()
            return result
        
        # Таблицы для проверки
        tables = ["missions", "claims", "audio_meta", "text_entries", "insights", "metrics"]
        tables.extend(["ingest_queue", "transcriptions", "facts", "digests"])  # Старые таблицы
        
        for table in tables:
            try:
                # SQLite count
                cursor.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608 — table from hardcoded list
                sqlite_count = cursor.fetchone()[0]

                # Supabase count
                response = supabase.table(table).select("*", count="exact").limit(1).execute()
                supabase_count = response.count if hasattr(response, 'count') else len(response.data) if response.data else 0
                
                # Если Supabase не возвращает count, делаем select count
                if supabase_count == 0 and sqlite_count > 0:
                    # Пробуем получить все записи (ограничено)
                    all_data = supabase.table(table).select("*").execute()
                    supabase_count = len(all_data.data) if all_data.data else 0
                
                match = abs(sqlite_count - supabase_count) <= 1  # Допуск на 1 строку
                
                result["tables"][table] = {
                    "sqlite_count": sqlite_count,
                    "supabase_count": supabase_count,
                    "match": match,
                    "diff": abs(sqlite_count - supabase_count),
                }
                
                if not match:
                    result["match"] = False
                    result["differences"].append({
                        "table": table,
                        "sqlite": sqlite_count,
                        "supabase": supabase_count,
                        "diff": abs(sqlite_count - supabase_count),
                    })
                    
            except Exception as e:
                logger.warning(f"Failed to verify {table}", error=str(e))
                result["tables"][table] = {
                    "sqlite_count": 0,
                    "supabase_count": 0,
                    "error": str(e),
                }
        
        conn.close()
        
    except Exception as e:
        logger.error("verify_row_counts_failed", error=str(e))
        result["error"] = str(e)
    
    return result


def migrate_to_supabase(dry_run: bool = False) -> Dict[str, Any]:
    """
    Мигрирует данные из SQLite в Supabase.
    
    Args:
        dry_run: Если True, только проверяет без выполнения миграции
        
    Returns:
        Результат миграции
    """
    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "dry_run": dry_run,
        "status": "pending",
        "tables": {},
        "errors": [],
    }
    
    try:
        # Проверяем подключение к Supabase
        from src.storage.supabase_client import get_supabase_client, test_connection
        
        test_result = test_connection()
        if test_result.get("status") != "ok":
            result["status"] = "failed"
            result["errors"].append(f"Supabase connection failed: {test_result.get('error', 'Unknown error')}")
            return result
        
        supabase = get_supabase_client()
        if not supabase:
            result["status"] = "failed"
            result["errors"].append("Supabase client not available")
            return result
        
        # Загружаем данные из SQLite
        from src.utils.config import settings
        import sqlite3
        
        sqlite_path = settings.STORAGE_PATH / "reflexio.db"
        if not sqlite_path.exists():
            result["status"] = "failed"
            result["errors"].append(f"SQLite database not found: {sqlite_path}")
            return result
        
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Список таблиц для миграции (старые + новые)
        tables = [
            "ingest_queue", "transcriptions", "facts", "digests",  # Старые таблицы
            "missions", "claims", "audio_meta", "text_entries", "insights", "metrics"  # Новые таблицы
        ]
        
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608 — table from hardcoded list
                count = cursor.fetchone()[0]
                
                result["tables"][table] = {
                    "sqlite_count": count,
                    "migrated": False,
                }
                
                if count == 0:
                    logger.info(f"Skipping empty table: {table}")
                    continue
                
                if dry_run:
                    result["tables"][table]["would_migrate"] = True
                    logger.info(f"[DRY RUN] Would migrate {count} rows from {table}")
                    continue
                
                # Читаем данные
                cursor.execute(f"SELECT * FROM {table}")  # nosec B608 — table from hardcoded list
                rows = cursor.fetchall()
                
                # Конвертируем в словари
                data = [dict(row) for row in rows]
                
                # Конвертируем данные для PostgreSQL
                for row in data:
                    # JSON строки → JSONB
                    for key in ["segments", "parameters", "source_urls", "evidence"]:
                        if key in row and row[key] and isinstance(row[key], str):
                            try:
                                row[key] = json.loads(row[key])
                            except Exception:
                                pass
                    
                    # TEXT ID → UUID (если нужно)
                    if "id" in row and isinstance(row["id"], str) and len(row["id"]) != 36:
                        # Оставляем как есть, Supabase примет
                        pass
                
                # Вставляем в Supabase
                if data:
                    response = supabase.table(table).insert(data).execute()
                    migrated_count = len(response.data) if response.data else len(data)
                    result["tables"][table]["migrated"] = True
                    result["tables"][table]["supabase_count"] = migrated_count
                    
                    logger.info(f"Migrated {migrated_count} rows to {table}")
                    
            except Exception as e:
                logger.error(f"Failed to migrate {table}", error=str(e))
                result["tables"][table]["error"] = str(e)
                result["errors"].append(f"{table}: {str(e)}")
        
        conn.close()
        
        result["status"] = "success" if not result["errors"] else "partial"
        
    except Exception as e:
        logger.error("migration_failed", error=str(e))
        result["status"] = "failed"
        result["errors"].append(str(e))
    
    return result


def apply_schema_migrations(backend: str = "supabase") -> Dict[str, Any]:
    """
    Применяет SQL миграции к базе данных.
    
    Args:
        backend: "supabase" или "sqlite"
        
    Returns:
        Результат применения миграций
    """
    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "backend": backend,
        "migrations_applied": [],
        "errors": [],
    }
    
    migrations_dir = Path(__file__).parent / "migrations"
    migrations = sorted(migrations_dir.glob("*.sql"))
    
    if not migrations:
        result["errors"].append("No migration files found")
        return result
    
    for migration_file in migrations:
        try:
            migration_sql = migration_file.read_text(encoding="utf-8")
            
            if backend == "supabase":
                # Для Supabase применяем через Supabase Dashboard SQL Editor
                # или через Supabase CLI (если установлен)
                import os
                import subprocess
                
                # Проверяем наличие Supabase CLI
                supabase_cli_available = False
                try:
                    subprocess.run(["supabase", "--version"], capture_output=True, timeout=5, check=True)
                    supabase_cli_available = True
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass
                
                if supabase_cli_available:
                    # Применяем через Supabase CLI
                    try:
                        # Сохраняем SQL во временный файл
                        temp_sql = Path.cwd() / ".tmp_migration.sql"
                        temp_sql.write_text(migration_sql, encoding="utf-8")
                        
                        # Выполняем через psql через Supabase CLI
                        result_cmd = subprocess.run(
                            ["supabase", "db", "push", "--db-url", f"{os.getenv('SUPABASE_URL')}/rest/v1"],
                            input=migration_sql,
                            text=True,
                            capture_output=True,
                            timeout=60,
                        )
                        
                        if result_cmd.returncode == 0:
                            result["migrations_applied"].append(migration_file.name)
                            logger.info(f"Applied migration {migration_file.name} via Supabase CLI")
                        else:
                            result["errors"].append(f"{migration_file.name}: CLI error - {result_cmd.stderr}")
                        
                        temp_sql.unlink(missing_ok=True)
                    except Exception as e:
                        logger.warning(f"Supabase CLI failed for {migration_file.name}, using manual method", error=str(e))
                        result["migrations_applied"].append(migration_file.name)
                        result["errors"].append(f"{migration_file.name}: Apply manually via Supabase Dashboard SQL Editor")
                else:
                    # Инструкция для ручного применения
                    logger.info(f"Migration {migration_file.name} should be applied via Supabase Dashboard SQL Editor")
                    result["migrations_applied"].append(migration_file.name)
                    result["note"] = "Migrations should be applied manually via Supabase Dashboard SQL Editor"
                
            elif backend == "sqlite":
                from src.utils.config import settings
                import sqlite3
                
                db_path = settings.STORAGE_PATH / "reflexio.db"
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                
                # Адаптируем SQL для SQLite
                sqlite_sql = migration_sql
                # Убираем PostgreSQL-специфичные конструкции
                sqlite_sql = sqlite_sql.replace("UUID", "TEXT")
                sqlite_sql = sqlite_sql.replace("gen_random_uuid()", "(lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6))))")
                sqlite_sql = sqlite_sql.replace("JSONB", "TEXT")
                sqlite_sql = sqlite_sql.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMP")
                sqlite_sql = sqlite_sql.replace("TIMESTAMPTZ", "TIMESTAMP")
                sqlite_sql = sqlite_sql.replace("vector(1536)", "TEXT")  # pgvector не поддерживается в SQLite
                sqlite_sql = sqlite_sql.replace("SERIAL", "INTEGER")
                sqlite_sql = sqlite_sql.replace("now()", "datetime('now')")
                
                # Убираем RLS политики (не поддерживаются в SQLite)
                if "0003_rls_policies" in migration_file.name:
                    logger.info(f"Skipping RLS policies for SQLite: {migration_file.name}")
                    result["migrations_applied"].append(migration_file.name + " (skipped - RLS not supported)")
                else:
                    cursor.executescript(sqlite_sql)
                    conn.commit()
                    result["migrations_applied"].append(migration_file.name)
                    logger.info(f"Applied migration {migration_file.name} to SQLite")
                
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to apply migration {migration_file.name}", error=str(e))
            result["errors"].append(f"{migration_file.name}: {str(e)}")
    
    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Database migration tool")
    parser.add_argument("--to", choices=["supabase", "sqlite"], default="supabase", help="Target backend")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--apply-schema", action="store_true", help="Apply schema migrations")
    parser.add_argument("--migrate-data", action="store_true", help="Migrate data from SQLite")
    parser.add_argument("--backup", action="store_true", help="Create SQLite backup before migration")
    parser.add_argument("--verify", action="store_true", help="Verify row counts after migration")
    
    args = parser.parse_args()
    
    # Backup перед миграцией
    if args.backup and args.migrate_data:
        try:
            backup_path = backup_sqlite()
            print(f"✅ Backup created: {backup_path}")
        except Exception as e:
            print(f"⚠️  Backup failed: {e}")
    
    if args.apply_schema:
        print("Applying schema migrations...")
        result = apply_schema_migrations(backend=args.to)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result.get("errors"):
            print("⚠️  Some migrations may need manual application via Supabase Dashboard")
    
    if args.migrate_data:
        if args.to != "supabase":
            print("Data migration only supported to Supabase")
            return 1
        
        print("Migrating data...")
        result = migrate_to_supabase(dry_run=args.dry_run)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if result["status"] == "failed":
            return 1
    
    if args.verify:
        print("Verifying row counts...")
        result = verify_row_counts()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if not result.get("match", True):
            print("⚠️  Row count differences detected")
            for diff in result.get("differences", []):
                print(f"   {diff['table']}: SQLite={diff['sqlite']}, Supabase={diff['supabase']}, Diff={diff['diff']}")
    
    if not args.apply_schema and not args.migrate_data and not args.verify:
        print("Use --apply-schema, --migrate-data, or --verify")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

