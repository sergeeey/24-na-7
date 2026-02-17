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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


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

    def __init__(self, db_path: str | Path = "src/storage/reflexio.db"):
        """Инициализация retention policy.

        Args:
            db_path: Путь к database
        """
        self.db_path = Path(db_path)
        self.rules = self.DEFAULT_RULES.copy()

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

            if not dry_run:
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
        """Cleanup одной таблицы.

        Args:
            cursor: Database cursor
            rule: Retention rule
            dry_run: Dry run mode

        Returns:
            Количество удалённых записей
        """
        cutoff_date = datetime.now() - timedelta(days=rule.retention_days)

        # Проверяем существование таблицы
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (rule.table,)
        )
        if not cursor.fetchone():
            return 0

        # Подсчёт expired records
        count_query = f"""
            SELECT COUNT(*) FROM {rule.table}
            WHERE {rule.timestamp_column} < ?
        """

        cursor.execute(count_query, (cutoff_date,))
        count = cursor.fetchone()[0]

        if count == 0 or dry_run:
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

        return count

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

__all__ = ["RetentionPolicy", "RetentionRule", "apply_retention"]
