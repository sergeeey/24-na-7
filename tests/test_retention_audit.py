"""Tests для retention audit trail."""
import pytest
import sqlite3
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

    # Create test transcriptions table
    cursor.execute("""
        CREATE TABLE transcriptions (
            id INTEGER PRIMARY KEY,
            text TEXT,
            created_at TIMESTAMP
        )
    """)

    # Insert test data (some expired, some not)
    now = datetime.now()
    old_date = now - timedelta(days=100)  # Beyond 90d retention
    recent_date = now - timedelta(days=10)  # Within 90d retention

    cursor.execute(
        "INSERT INTO transcriptions (id, text, created_at) VALUES (?, ?, ?)",
        (1, "old record 1", old_date),
    )
    cursor.execute(
        "INSERT INTO transcriptions (id, text, created_at) VALUES (?, ?, ?)",
        (2, "old record 2", old_date),
    )
    cursor.execute(
        "INSERT INTO transcriptions (id, text, created_at) VALUES (?, ?, ?)",
        (3, "recent record", recent_date),
    )

    conn.commit()
    conn.close()

    return db_path


class TestRetentionAudit:
    """Tests для audit trail."""

    def test_audit_log_created_on_cleanup(self, test_db):
        """Тест: audit log создаётся при cleanup."""
        policy = RetentionPolicy(db_path=test_db)

        # Run cleanup
        results = policy.cleanup_expired_data(dry_run=False)

        assert results["transcriptions"] == 2  # 2 expired records

        # Check audit log
        audit_logs = policy.get_audit_log(limit=10)

        assert len(audit_logs) > 0
        latest_log = audit_logs[0]

        assert latest_log["table_name"] == "transcriptions"
        assert latest_log["operation"] == "DELETE"
        assert latest_log["record_count"] == 2
        assert latest_log["dry_run"] == 0
        assert latest_log["error_message"] is None

    def test_audit_log_dry_run(self, test_db):
        """Тест: audit log создаётся даже в dry_run mode."""
        policy = RetentionPolicy(db_path=test_db)

        # Dry run
        results = policy.cleanup_expired_data(dry_run=True)

        assert results["transcriptions"] == 2

        # Check audit log
        audit_logs = policy.get_audit_log(limit=10)

        assert len(audit_logs) > 0
        latest_log = audit_logs[0]

        assert latest_log["dry_run"] == 1
        assert latest_log["record_count"] == 2

        # Verify no actual deletion
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transcriptions")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 3  # No deletions in dry_run

    def test_audit_log_deleted_ids(self, test_db):
        """Тест: deleted IDs логируются."""
        policy = RetentionPolicy(db_path=test_db)

        # Cleanup
        policy.cleanup_expired_data(dry_run=False)

        # Check audit log
        audit_logs = policy.get_audit_log(limit=1)
        latest_log = audit_logs[0]

        # Deleted IDs should be JSON array
        import json
        deleted_ids = json.loads(latest_log["deleted_ids"])

        assert len(deleted_ids) == 2
        assert 1 in deleted_ids
        assert 2 in deleted_ids

    def test_audit_log_filter_by_table(self, test_db):
        """Тест: фильтрация audit log по таблице."""
        policy = RetentionPolicy(db_path=test_db)

        # Cleanup
        policy.cleanup_expired_data(dry_run=False)

        # Filter by table
        audit_logs = policy.get_audit_log(limit=10, table_filter="transcriptions")

        assert len(audit_logs) > 0
        assert all(log["table_name"] == "transcriptions" for log in audit_logs)

    def test_audit_log_filter_by_date(self, test_db):
        """Тест: фильтрация audit log по дате."""
        policy = RetentionPolicy(db_path=test_db)

        # First cleanup
        policy.cleanup_expired_data(dry_run=True)

        # Wait and second cleanup
        import time
        time.sleep(0.1)

        cutoff = datetime.now()
        time.sleep(0.1)

        policy.cleanup_expired_data(dry_run=True)

        # Filter by date
        recent_logs = policy.get_audit_log(limit=10, since=cutoff)

        assert len(recent_logs) >= 1

    def test_audit_log_zero_deletions(self, test_db):
        """Тест: audit log даже при 0 deletions (для мониторинга)."""
        # Create DB with no expired data
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()

        # Clear old data
        cursor.execute("DELETE FROM transcriptions WHERE id IN (1, 2)")
        conn.commit()
        conn.close()

        policy = RetentionPolicy(db_path=test_db)

        # Cleanup (should delete 0 records)
        results = policy.cleanup_expired_data(dry_run=False)

        assert results["transcriptions"] == 0

        # Audit log should still exist
        audit_logs = policy.get_audit_log(limit=1)

        assert len(audit_logs) > 0
        assert audit_logs[0]["record_count"] == 0

    def test_audit_log_retention_rule_stored(self, test_db):
        """Тест: retention rule сохраняется в audit log."""
        policy = RetentionPolicy(db_path=test_db)

        # Cleanup
        policy.cleanup_expired_data(dry_run=False)

        # Check rule in audit log
        audit_logs = policy.get_audit_log(limit=1)
        latest_log = audit_logs[0]

        import json
        rule = json.loads(latest_log["retention_rule"])

        assert rule["table"] == "transcriptions"
        assert rule["retention_days"] == 90
        assert rule["timestamp_column"] == "created_at"

    def test_multiple_cleanups_tracked(self, test_db):
        """Тест: несколько cleanup operations tracked."""
        policy = RetentionPolicy(db_path=test_db)

        # Multiple cleanups
        policy.cleanup_expired_data(dry_run=True)
        policy.cleanup_expired_data(dry_run=True)
        policy.cleanup_expired_data(dry_run=False)

        # Check audit log count
        audit_logs = policy.get_audit_log(limit=100)

        # Should have entries for each cleanup (transcriptions + facts + digests)
        # 3 cleanups × 3 tables = 9 entries (but facts/digests tables don't exist, so just transcriptions)
        transcription_logs = [log for log in audit_logs if log["table_name"] == "transcriptions"]

        assert len(transcription_logs) >= 3

    def test_audit_log_limit(self, test_db):
        """Тест: limit parameter работает."""
        policy = RetentionPolicy(db_path=test_db)

        # Create multiple entries
        for _ in range(5):
            policy.cleanup_expired_data(dry_run=True)

        # Limit to 2
        audit_logs = policy.get_audit_log(limit=2)

        assert len(audit_logs) <= 2

    def test_audit_log_ordering(self, test_db):
        """Тест: audit log упорядочен по executed_at DESC."""
        policy = RetentionPolicy(db_path=test_db)

        # Multiple cleanups with time gap
        import time

        policy.cleanup_expired_data(dry_run=True)
        time.sleep(0.1)
        policy.cleanup_expired_data(dry_run=True)

        # Get logs
        audit_logs = policy.get_audit_log(limit=10)

        # Check ordering (newer first)
        if len(audit_logs) >= 2:
            assert audit_logs[0]["executed_at"] >= audit_logs[1]["executed_at"]
