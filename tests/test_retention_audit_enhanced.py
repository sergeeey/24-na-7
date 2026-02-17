"""Tests для enhanced retention audit trail (v4.1.1)."""
import pytest
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

from src.storage.retention import RetentionPolicy, RetentionRule


@pytest.fixture
def test_db(tmp_path):
    """Temporary test database."""
    db_path = tmp_path / "test_retention.db"

    # Create test table with data
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE transcriptions (
            id INTEGER PRIMARY KEY,
            text TEXT,
            created_at TIMESTAMP
        )
    """)

    # Insert test data
    now = datetime.now()
    old_date = now - timedelta(days=100)

    for i in range(1, 11):
        cursor.execute(
            "INSERT INTO transcriptions (id, text, created_at) VALUES (?, ?, ?)",
            (i, f"old record {i}", old_date),
        )

    conn.commit()
    conn.close()

    return db_path


class TestRetentionAuditEnhanced:
    """Тесты для enhanced audit trail fields (v4.1.1)."""

    def test_audit_log_execution_context(self, test_db):
        """Тест: execution context (job_run_id, job_name, trigger, actor)."""
        policy = RetentionPolicy(
            db_path=test_db,
            job_name="test_cleanup",
            trigger="manual",
            actor="test_user",
            environment="test",
        )

        # Run cleanup
        policy.cleanup_expired_data(dry_run=False)

        # Check audit log
        audit_logs = policy.get_audit_log(limit=1, table_filter="transcriptions")
        latest_log = audit_logs[0]

        # Verify execution context
        assert latest_log["job_run_id"] is not None
        assert len(latest_log["job_run_id"]) == 36  # UUID format
        assert latest_log["job_name"] == "test_cleanup"
        assert latest_log["trigger"] == "manual"
        assert latest_log["actor"] == "test_user"

    def test_audit_log_environment_context(self, test_db):
        """Тест: environment context (environment, host, app_version, db_schema_version)."""
        policy = RetentionPolicy(db_path=test_db, environment="staging")

        policy.cleanup_expired_data(dry_run=False)

        audit_logs = policy.get_audit_log(limit=1, table_filter="transcriptions")
        latest_log = audit_logs[0]

        # Verify environment context
        assert latest_log["environment"] == "staging"
        assert latest_log["host"] is not None
        assert latest_log["app_version"] is not None
        assert latest_log["db_schema_version"] == "0004"

    def test_audit_log_performance_metrics(self, test_db):
        """Тест: performance metrics (duration_ms, rows_scanned)."""
        policy = RetentionPolicy(db_path=test_db)

        policy.cleanup_expired_data(dry_run=False)

        audit_logs = policy.get_audit_log(limit=1, table_filter="transcriptions")
        latest_log = audit_logs[0]

        # Verify performance metrics
        assert latest_log["duration_ms"] is not None
        assert latest_log["duration_ms"] >= 0
        assert latest_log["rows_scanned"] == 10  # 10 записей deleted

    def test_audit_log_id_range(self, test_db):
        """Тест: ID range (min_deleted_id, max_deleted_id)."""
        policy = RetentionPolicy(db_path=test_db)

        policy.cleanup_expired_data(dry_run=False)

        audit_logs = policy.get_audit_log(limit=1, table_filter="transcriptions")
        latest_log = audit_logs[0]

        # Verify ID range
        assert latest_log["min_deleted_id"] == 1
        assert latest_log["max_deleted_id"] == 10

    def test_audit_log_json_fields_valid(self, test_db):
        """Тест: retention_rule и deleted_ids как валидный JSON."""
        policy = RetentionPolicy(db_path=test_db)

        policy.cleanup_expired_data(dry_run=False)

        audit_logs = policy.get_audit_log(limit=1, table_filter="transcriptions")
        latest_log = audit_logs[0]

        # Parse retention_rule
        rule = json.loads(latest_log["retention_rule"])
        assert rule["table"] == "transcriptions"
        assert rule["retention_days"] == 90

        # Parse deleted_ids
        deleted_ids = json.loads(latest_log["deleted_ids"])
        assert isinstance(deleted_ids, list)
        assert len(deleted_ids) == 10
        assert 1 in deleted_ids
        assert 10 in deleted_ids

    def test_job_run_id_consistency(self, test_db):
        """Тест: job_run_id одинаковый для всех операций в одном запуске."""
        policy = RetentionPolicy(db_path=test_db)

        policy.cleanup_expired_data(dry_run=False)

        # Get all audit logs для этого запуска
        audit_logs = policy.get_audit_log(limit=10)

        # Все logs должны иметь одинаковый job_run_id
        job_run_ids = {log["job_run_id"] for log in audit_logs}
        assert len(job_run_ids) == 1  # Только один unique job_run_id

    def test_dry_run_performance_tracked(self, test_db):
        """Тест: performance metrics трекается даже в dry_run mode."""
        policy = RetentionPolicy(db_path=test_db)

        policy.cleanup_expired_data(dry_run=True)

        audit_logs = policy.get_audit_log(limit=1, table_filter="transcriptions")
        latest_log = audit_logs[0]

        assert latest_log["dry_run"] == 1
        assert latest_log["duration_ms"] is not None
        assert latest_log["duration_ms"] >= 0
        assert latest_log["rows_scanned"] == 10  # Scanned но не deleted

    def test_error_case_performance_tracked(self, test_db):
        """Тест: performance metrics трекается даже при ошибке."""
        # Create policy с несуществующей таблицей
        policy = RetentionPolicy(db_path=test_db)
        policy.rules = [RetentionRule(table="nonexistent", retention_days=90)]

        policy.cleanup_expired_data(dry_run=False)

        audit_logs = policy.get_audit_log(limit=1)
        latest_log = audit_logs[0]

        # Verify error tracked с performance metrics
        assert latest_log["error_message"] == "Table does not exist"
        assert latest_log["duration_ms"] is not None
        assert latest_log["duration_ms"] >= 0

    def test_audit_indexes_created(self, test_db):
        """Тест: индексы создаются автоматически."""
        policy = RetentionPolicy(db_path=test_db)
        policy.cleanup_expired_data(dry_run=False)

        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()

        # Check indexes exist
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='retention_audit_log'
        """)
        indexes = {row[0] for row in cursor.fetchall()}

        expected_indexes = {
            "idx_audit_job_run_id",
            "idx_audit_environment",
            "idx_audit_trigger",
        }

        assert expected_indexes.issubset(indexes)
        conn.close()

    def test_compliance_query_by_environment(self, test_db):
        """Тест: query audit logs по environment (compliance use case)."""
        policy = RetentionPolicy(db_path=test_db, environment="production")
        policy.cleanup_expired_data(dry_run=False)

        # Query только production logs
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM retention_audit_log
            WHERE environment = 'production'
        """)
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 1  # Хотя бы transcriptions log

    def test_compliance_query_by_job_run(self, test_db):
        """Тест: query всех операций одного job run (troubleshooting use case)."""
        policy = RetentionPolicy(db_path=test_db)
        job_run_id = policy.job_run_id

        policy.cleanup_expired_data(dry_run=False)

        # Query все операции этого job run
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name, record_count, duration_ms
            FROM retention_audit_log
            WHERE job_run_id = ?
        """, (job_run_id,))
        results = cursor.fetchall()
        conn.close()

        # Должны быть операции для transcriptions, facts, digests
        assert len(results) >= 1
        # Verify данные
        for table_name, record_count, duration_ms in results:
            assert table_name in ["transcriptions", "facts", "digests"]
            assert duration_ms is not None

    def test_performance_analysis_query(self, test_db):
        """Тест: query для performance analysis."""
        policy = RetentionPolicy(db_path=test_db)
        policy.cleanup_expired_data(dry_run=False)

        # Query average duration по таблицам
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name, AVG(duration_ms), SUM(rows_scanned)
            FROM retention_audit_log
            WHERE error_message IS NULL
            GROUP BY table_name
        """)
        results = cursor.fetchall()
        conn.close()

        assert len(results) >= 1
        for table_name, avg_duration, total_scanned in results:
            assert avg_duration is not None
            assert total_scanned is not None
