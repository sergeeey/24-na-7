"""Тесты для Prometheus metrics (v4.1)."""
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.monitoring.prometheus_metrics import PrometheusMetrics


class TestPrometheusMetrics:
    """Тесты для PrometheusMetrics collector."""

    @pytest.fixture
    def test_db(self):
        """Создать тестовую БД с данными."""
        # Create temp db
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "test_metrics.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create tables
        cursor.execute("""
            CREATE TABLE transcriptions (
                id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE facts (
                id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_hallucination INTEGER DEFAULT 0,
                is_atomic INTEGER DEFAULT 1,
                cove_confidence REAL,
                cove_verification_rounds INTEGER,
                citation_coverage REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE digests (
                id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE retention_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                operation TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                deleted_ids TEXT,
                retention_rule TEXT,
                cutoff_date TIMESTAMP,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                dry_run BOOLEAN DEFAULT 0,
                error_message TEXT
            )
        """)

        # Insert test data
        now = datetime.now()
        yesterday = now - timedelta(hours=24)

        # Transcriptions
        cursor.execute("INSERT INTO transcriptions (created_at) VALUES (?)", (now,))
        cursor.execute("INSERT INTO transcriptions (created_at) VALUES (?)", (yesterday,))

        # Facts (10 total: 9 good, 1 hallucination)
        for i in range(9):
            cursor.execute("""
                INSERT INTO facts (created_at, is_hallucination, is_atomic, cove_confidence, cove_verification_rounds, citation_coverage)
                VALUES (?, 0, 1, ?, 1, 0.98)
            """, (now, 0.85 + i * 0.01))

        cursor.execute("""
            INSERT INTO facts (created_at, is_hallucination, is_atomic, cove_confidence, cove_verification_rounds, citation_coverage)
            VALUES (?, 1, 1, 0.62, 2, 0.45)
        """, (now,))

        # Digests
        cursor.execute("INSERT INTO digests (created_at) VALUES (?)", (now,))

        # Retention audit log (last 7 days)
        cursor.execute("""
            INSERT INTO retention_audit_log (table_name, operation, record_count, executed_at, dry_run)
            VALUES ('transcriptions', 'DELETE', 5, ?, 0)
        """, (now - timedelta(days=2),))

        cursor.execute("""
            INSERT INTO retention_audit_log (table_name, operation, record_count, executed_at, dry_run, error_message)
            VALUES ('facts', 'DELETE', 0, ?, 0, 'Table does not exist')
        """, (now - timedelta(days=1),))

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        db_path.unlink()

    def test_collect_core_metrics(self, test_db):
        """Тест: базовые метрики (counts)."""
        collector = PrometheusMetrics(db_path=test_db)
        metrics = collector.collect_all_metrics()

        assert "reflexio_transcriptions_total 2" in metrics
        assert "reflexio_facts_total 10" in metrics
        assert "reflexio_digests_total 1" in metrics

    def test_collect_cove_metrics(self, test_db):
        """Тест: CoVe метрики."""
        collector = PrometheusMetrics(db_path=test_db)
        metrics = collector.collect_all_metrics()

        # CoVe enabled (should be 0 by default unless ENABLE_COVE=true)
        assert "reflexio_cove_enabled" in metrics

        # Average confidence (9 facts @ 0.85-0.93 + 1 @ 0.62 = avg ~0.81)
        assert "reflexio_cove_avg_confidence_24h" in metrics
        # Проверим что значение разумное (0.7-0.9)
        for line in metrics.split("\n"):
            if line.startswith("reflexio_cove_avg_confidence_24h"):
                value = float(line.split()[1])
                assert 0.7 <= value <= 0.9

        # Average verification rounds (9×1 + 1×2 = 11/10 = 1.1)
        assert "reflexio_cove_avg_verification_rounds_24h" in metrics

    def test_collect_fact_metrics(self, test_db):
        """Тест: Fact quality метрики."""
        collector = PrometheusMetrics(db_path=test_db)
        metrics = collector.collect_all_metrics()

        # Hallucination rate (1/10 = 0.1)
        assert "reflexio_hallucination_rate_24h" in metrics
        for line in metrics.split("\n"):
            if line.startswith("reflexio_hallucination_rate_24h"):
                value = float(line.split()[1])
                assert value == 0.1  # 1 hallucination из 10

        # Citation coverage (9×0.98 + 1×0.45 = 9.27/10 = 0.927)
        assert "reflexio_citation_coverage_24h" in metrics

        # Atomicity violations (0, все atomic)
        assert "reflexio_atomicity_violations_24h 0" in metrics

    def test_collect_retention_metrics(self, test_db):
        """Тест: Retention операции метрики."""
        collector = PrometheusMetrics(db_path=test_db)
        metrics = collector.collect_all_metrics()

        # Total operations (2 в последние 7 дней)
        assert "reflexio_retention_operations_7d 2" in metrics

        # Deleted records (5, только из первой операции, вторая error)
        assert "reflexio_retention_deleted_records_7d 5" in metrics

        # Errors (1, вторая операция с error_message)
        assert "reflexio_retention_errors_7d 1" in metrics

    def test_collect_process_lock_metrics_no_locks(self, test_db):
        """Тест: ProcessLock метрики (без locks)."""
        collector = PrometheusMetrics(db_path=test_db)
        metrics = collector.collect_all_metrics()

        # Без locks — метрики могут отсутствовать (директория не существует)
        # Просто проверим, что метод не падает
        assert isinstance(metrics, str)
        assert len(metrics) > 0

    def test_prometheus_format_valid(self, test_db):
        """Тест: Prometheus format корректен."""
        collector = PrometheusMetrics(db_path=test_db)
        metrics = collector.collect_all_metrics()

        lines = metrics.split("\n")

        # Проверим структуру: HELP → TYPE → VALUE
        help_count = sum(1 for line in lines if line.startswith("# HELP"))
        type_count = sum(1 for line in lines if line.startswith("# TYPE"))
        value_count = sum(1 for line in lines if line and not line.startswith("#"))

        assert help_count > 0
        assert type_count > 0
        assert value_count > 0

        # help_count должен быть равен type_count (каждая метрика имеет HELP и TYPE)
        assert help_count == type_count

    def test_empty_db_graceful(self):
        """Тест: Graceful handling для несуществующей БД."""
        temp_dir = Path(tempfile.mkdtemp())
        non_existent_db = temp_dir / "non_existent.db"

        collector = PrometheusMetrics(db_path=non_existent_db)
        metrics = collector.collect_all_metrics()

        # Должны вернуться базовые метрики (CoVe enabled, threshold)
        assert "reflexio_cove_enabled" in metrics
        assert "reflexio_cove_confidence_threshold" in metrics

        # Но не должно быть БД-зависимых метрик
        assert "reflexio_transcriptions_total" not in metrics

    def test_metric_labels_consistent(self, test_db):
        """Тест: Labels метрик консистентны."""
        collector = PrometheusMetrics(db_path=test_db)
        metrics = collector.collect_all_metrics()

        # Все метрики начинаются с "reflexio_"
        for line in metrics.split("\n"):
            if line and not line.startswith("#"):
                metric_name = line.split()[0]
                assert metric_name.startswith("reflexio_")
