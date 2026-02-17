"""Retention Policy — управление жизненным циклом данных.

Политики (TECH SPEC v4):
    - Raw Audio: 24 hours (delete after processing)
    - Transcriptions: 90 days
    - Facts: 2 years
    - Digests: 2 years

Использование:
    from src.storage.retention import RetentionPolicy, apply_retention

    policy = RetentionPolicy()
    deleted_count = policy.cleanup_expired_data()
"""

import sqlite3
import json
import logging
import os
import socket
import uuid
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class RetentionRule:
    """Правило retention для типа данных."""
    table: str
    retention_days: int
    timestamp_column: str = "created_at"
    soft_delete: bool = False
    delete_column: Optional[str] = "deleted_at"


class RetentionPolicy:
    """Retention policy manager.

    Attributes:
        db_path: Путь к SQLite database
        rules: Правила retention
    """

    # Retention rules по TECH SPEC v4
    DEFAULT_RULES = [
        RetentionRule(table="transcriptions", retention_days=90),
        RetentionRule(table="facts", retention_days=730),  # 2 years
        RetentionRule(table="digests", retention_days=730),  # 2 years
    ]

    def __init__(
        self,
        db_path: str | Path = "src/storage/reflexio.db",
        job_name: str = "retention_cleanup",
        trigger: str = "cron",
        actor: str = "system",
        environment: Optional[str] = None,
    ):
        """Инициализация retention policy.

        Args:
            db_path: Путь к database
            job_name: Имя job (для audit trail)
            trigger: Источник запуска (cron|manual|ci|api)
            actor: Кто/что запустило (system|username|service_account)
            environment: Окружение (dev|staging|prod), default из ENV
        """
        self.db_path = Path(db_path)
        self.rules = self.DEFAULT_RULES.copy()

        # Execution context для audit trail
        self.job_run_id = str(uuid.uuid4())
        self.job_name = job_name
        self.trigger = trigger
        self.actor = actor
        self.environment = environment or os.getenv("ENVIRONMENT", "dev")
        self.host = socket.gethostname()
        self.app_version = os.getenv("APP_VERSION", "v4.1")
        self.db_schema_version = "0004"  # Latest migration

    def cleanup_expired_data(self, dry_run: bool = False) -> Dict[str, int]:
        """Cleanup expired data по всем правилам.

        Args:
            dry_run: Если True — только подсчёт, без удаления

        Returns:
            Dict с количеством удалённых записей по таблицам
        """
        results = {}

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            for rule in self.rules:
                count = self._cleanup_table(cursor, rule, dry_run)
                results[rule.table] = count

            # ВСЕГДА коммитить audit log (даже в dry_run mode)
            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

        return results

    def _cleanup_table(
        self,
        cursor: sqlite3.Cursor,
        rule: RetentionRule,
        dry_run: bool,
    ) -> int:
        """Cleanup одной таблицы с audit logging.

        Args:
            cursor: Database cursor
            rule: Retention rule
            dry_run: Dry run mode

        Returns:
            Количество удалённых записей
        """
        start_time = time.time()  # Performance tracking
        cutoff_date = datetime.now() - timedelta(days=rule.retention_days)

        # Проверяем существование таблицы
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (rule.table,)
        )
        if not cursor.fetchone():
            # Log даже для несуществующих таблиц (для мониторинга)
            operation = "SOFT_DELETE" if rule.soft_delete else "DELETE"
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_audit(
                cursor, rule.table, operation, 0, [],
                rule, cutoff_date, dry_run, error_message="Table does not exist",
                duration_ms=duration_ms, rows_scanned=0
            )
            return 0

        # Получаем IDs для audit trail (до удаления)
        id_query = f"""
            SELECT id FROM {rule.table}
            WHERE {rule.timestamp_column} < ?
            LIMIT 1000
        """
        cursor.execute(id_query, (cutoff_date,))
        deleted_ids = [row[0] for row in cursor.fetchall()]

        # Подсчёт expired records
        count_query = f"""
            SELECT COUNT(*) FROM {rule.table}
            WHERE {rule.timestamp_column} < ?
        """
        cursor.execute(count_query, (cutoff_date,))
        count = cursor.fetchone()[0]

        operation = "SOFT_DELETE" if rule.soft_delete else "DELETE"
        error_message = None

        try:
            if count == 0:
                # Log даже при 0 deletions для мониторинга
                duration_ms = int((time.time() - start_time) * 1000)
                self._log_audit(
                    cursor, rule.table, operation, 0, [],
                    rule, cutoff_date, dry_run, error_message=None,
                    duration_ms=duration_ms, rows_scanned=0
                )
                return count

            if dry_run:
                # Dry run — только audit log
                duration_ms = int((time.time() - start_time) * 1000)
                self._log_audit(
                    cursor, rule.table, operation, count, deleted_ids,
                    rule, cutoff_date, dry_run=True, error_message=None,
                    duration_ms=duration_ms, rows_scanned=count
                )
                return count

            # Удаление (soft или hard)
            if rule.soft_delete and rule.delete_column:
                # Soft delete
                delete_query = f"""
                    UPDATE {rule.table}
                    SET {rule.delete_column} = ?
                    WHERE {rule.timestamp_column} < ?
                    AND {rule.delete_column} IS NULL
                """
                cursor.execute(delete_query, (datetime.now(), cutoff_date))
            else:
                # Hard delete
                delete_query = f"""
                    DELETE FROM {rule.table}
                    WHERE {rule.timestamp_column} < ?
                """
                cursor.execute(delete_query, (cutoff_date,))

            # Audit log успешного удаления
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_audit(
                cursor, rule.table, operation, count, deleted_ids,
                rule, cutoff_date, dry_run=False, error_message=None,
                duration_ms=duration_ms, rows_scanned=count
            )

            logger.info(
                f"Retention cleanup: {rule.table} — {count} records {operation} ({duration_ms}ms)"
            )

        except Exception as e:
            error_message = str(e)
            logger.error(f"Retention cleanup failed: {rule.table} — {e}")

            # Audit log ошибки
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_audit(
                cursor, rule.table, operation, 0, [],
                rule, cutoff_date, dry_run, error_message=error_message,
                duration_ms=duration_ms, rows_scanned=0
            )
            raise

        return count

    def _log_audit(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
        operation: str,
        record_count: int,
        deleted_ids: List[int],
        rule: RetentionRule,
        cutoff_date: datetime,
        dry_run: bool,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        rows_scanned: Optional[int] = None,
    ):
        """Логирование в audit trail (enhanced v4.1.1).

        Args:
            cursor: Database cursor
            table_name: Имя таблицы
            operation: Тип операции
            record_count: Количество удалённых записей
            deleted_ids: IDs удалённых записей
            rule: Retention rule
            cutoff_date: Cutoff date
            dry_run: Dry run mode
            error_message: Сообщение об ошибке (если есть)
            duration_ms: Время выполнения (миллисекунды)
            rows_scanned: Количество проверенных записей
        """
        # Ensure audit log table exists
        self._ensure_audit_table(cursor)

        # Serialize rule as JSON object (not string)
        rule_json = json.dumps(asdict(rule))

        # Serialize deleted IDs as JSON array (limit 1000)
        deleted_ids_json = json.dumps(deleted_ids[:1000])

        # Calculate ID range для больших datasets
        min_id = min(deleted_ids) if deleted_ids else None
        max_id = max(deleted_ids) if deleted_ids else None

        audit_query = """
            INSERT INTO retention_audit_log (
                table_name, operation, record_count, deleted_ids,
                retention_rule, cutoff_date, executed_at, dry_run, error_message,
                job_run_id, job_name, trigger, actor,
                environment, host, app_version, db_schema_version,
                duration_ms, rows_scanned, min_deleted_id, max_deleted_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        cursor.execute(
            audit_query,
            (
                table_name,
                operation,
                record_count,
                deleted_ids_json,
                rule_json,
                cutoff_date,
                datetime.now(),
                int(dry_run),
                error_message,
                # Execution context
                self.job_run_id,
                self.job_name,
                self.trigger,
                self.actor,
                # Environment context
                self.environment,
                self.host,
                self.app_version,
                self.db_schema_version,
                # Performance/scale
                duration_ms,
                rows_scanned,
                min_id,
                max_id,
            ),
        )

    def _ensure_audit_table(self, cursor: sqlite3.Cursor):
        """Создаёт audit log table если не существует (v4.1.1 schema)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retention_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                operation TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                deleted_ids TEXT,
                retention_rule TEXT,
                cutoff_date TIMESTAMP,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                dry_run BOOLEAN DEFAULT 0,
                error_message TEXT,
                -- Execution context (v4.1.1)
                job_run_id TEXT,
                job_name TEXT DEFAULT 'retention_cleanup',
                trigger TEXT DEFAULT 'cron',
                actor TEXT DEFAULT 'system',
                -- Environment context
                environment TEXT,
                host TEXT,
                app_version TEXT,
                db_schema_version TEXT,
                -- Performance/scale
                duration_ms INTEGER,
                rows_scanned INTEGER,
                min_deleted_id INTEGER,
                max_deleted_id INTEGER
            )
        """)

        # Create indexes if not exist
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_job_run_id
            ON retention_audit_log(job_run_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_environment
            ON retention_audit_log(environment)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_trigger
            ON retention_audit_log(trigger)
        """)

    def get_retention_stats(self) -> Dict[str, Any]:
        """Статистика retention.

        Returns:
            Dict с количеством записей и expired записей
        """
        stats = {}

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            for rule in self.rules:
                # Проверяем существование таблицы
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (rule.table,)
                )
                if not cursor.fetchone():
                    continue

                # Total count
                cursor.execute(f"SELECT COUNT(*) FROM {rule.table}")
                total = cursor.fetchone()[0]

                # Expired count
                cutoff_date = datetime.now() - timedelta(days=rule.retention_days)
                cursor.execute(
                    f"SELECT COUNT(*) FROM {rule.table} WHERE {rule.timestamp_column} < ?",
                    (cutoff_date,)
                )
                expired = cursor.fetchone()[0]

                stats[rule.table] = {
                    "total": total,
                    "expired": expired,
                    "retention_days": rule.retention_days,
                }

        finally:
            conn.close()

        return stats

    def get_audit_log(
        self,
        limit: int = 100,
        table_filter: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Получение audit log записей.

        Args:
            limit: Максимальное количество записей
            table_filter: Фильтр по таблице
            since: Показать только после этой даты

        Returns:
            Список audit log entries
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Ensure audit table exists перед запросом
            self._ensure_audit_table(cursor)

            query = "SELECT * FROM retention_audit_log WHERE 1=1"
            params = []

            if table_filter:
                query += " AND table_name = ?"
                params.append(table_filter)

            if since:
                query += " AND executed_at >= ?"
                params.append(since)

            query += " ORDER BY executed_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

        finally:
            conn.close()


def apply_retention(db_path: str | Path = "src/storage/reflexio.db", dry_run: bool = False) -> Dict[str, int]:
    """Применение retention policy (convenience function).

    Args:
        db_path: Путь к database
        dry_run: Dry run mode

    Returns:
        Dict с результатами
    """
    policy = RetentionPolicy(db_path)
    return policy.cleanup_expired_data(dry_run=dry_run)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "RetentionPolicy",
    "RetentionRule",
    "apply_retention",
    # Audit log будет доступен через RetentionPolicy.get_audit_log()
]
