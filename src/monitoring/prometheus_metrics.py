"""Prometheus metrics для v4.1 Production-Ready monitoring.

Метрики покрывают:
- CoVe hallucination detection (confidence, verification rounds)
- Fact extraction (atomicity, citation coverage, hallucination rate)
- Retention operations (deleted records, errors)
- ProcessLock (acquisitions, stale locks)
"""
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("monitoring.prometheus")


class PrometheusMetrics:
    """Сборщик Prometheus-compatible метрик для v4.1."""

    def __init__(self, db_path: Optional[Path] = None):
        """Инициализация.

        Args:
            db_path: Путь к БД (default: settings.STORAGE_PATH / "reflexio.db")
        """
        self.db_path = db_path or (settings.STORAGE_PATH / "reflexio.db")

    def collect_all_metrics(self) -> str:
        """Собрать все метрики в Prometheus format.

        Returns:
            String в Prometheus exposition format
        """
        metrics = []

        # Core metrics
        metrics.extend(self._collect_core_metrics())

        # CoVe metrics
        metrics.extend(self._collect_cove_metrics())

        # Fact extraction metrics
        metrics.extend(self._collect_fact_metrics())

        # Retention metrics
        metrics.extend(self._collect_retention_metrics())

        # ProcessLock metrics
        metrics.extend(self._collect_process_lock_metrics())

        return "\n".join(metrics) + "\n"

    def _collect_core_metrics(self) -> List[str]:
        """Базовые метрики (counts)."""
        metrics = []

        if not self.db_path.exists():
            return metrics

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Transcriptions count
            cursor.execute("SELECT COUNT(*) FROM transcriptions")
            transcriptions_count = cursor.fetchone()[0]

            metrics.append("# HELP reflexio_transcriptions_total Total transcriptions")
            metrics.append("# TYPE reflexio_transcriptions_total counter")
            metrics.append(f"reflexio_transcriptions_total {transcriptions_count}")

            # Facts count
            cursor.execute("SELECT COUNT(*) FROM facts")
            facts_count = cursor.fetchone()[0]

            metrics.append("# HELP reflexio_facts_total Total facts extracted")
            metrics.append("# TYPE reflexio_facts_total counter")
            metrics.append(f"reflexio_facts_total {facts_count}")

            # Digests count
            cursor.execute("SELECT COUNT(*) FROM digests")
            digests_count = cursor.fetchone()[0]

            metrics.append("# HELP reflexio_digests_total Total digests generated")
            metrics.append("# TYPE reflexio_digests_total counter")
            metrics.append(f"reflexio_digests_total {digests_count}")

            conn.close()

        except Exception as e:
            logger.error(f"core_metrics_collection_failed: {e}")

        return metrics

    def _collect_cove_metrics(self) -> List[str]:
        """CoVe (Chain-of-Verification) метрики."""
        metrics = []

        # CoVe enabled flag
        cove_enabled = 1 if settings.ENABLE_COVE else 0
        metrics.append("# HELP reflexio_cove_enabled CoVe feature enabled (1=yes, 0=no)")
        metrics.append("# TYPE reflexio_cove_enabled gauge")
        metrics.append(f"reflexio_cove_enabled {cove_enabled}")

        # CoVe confidence threshold
        metrics.append("# HELP reflexio_cove_confidence_threshold CoVe confidence threshold")
        metrics.append("# TYPE reflexio_cove_confidence_threshold gauge")
        metrics.append(f"reflexio_cove_confidence_threshold {settings.COVE_CONFIDENCE_THRESHOLD}")

        if not self.db_path.exists():
            return metrics

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Average CoVe confidence (last 24h)
            cutoff = datetime.now() - timedelta(hours=24)
            cursor.execute("""
                SELECT AVG(cove_confidence)
                FROM facts
                WHERE created_at >= ? AND cove_confidence IS NOT NULL
            """, (cutoff,))
            avg_confidence = cursor.fetchone()[0]

            if avg_confidence is not None:
                metrics.append("# HELP reflexio_cove_avg_confidence_24h Average CoVe confidence (last 24h)")
                metrics.append("# TYPE reflexio_cove_avg_confidence_24h gauge")
                metrics.append(f"reflexio_cove_avg_confidence_24h {avg_confidence:.4f}")

            # CoVe verification rounds (avg, last 24h)
            cursor.execute("""
                SELECT AVG(cove_verification_rounds)
                FROM facts
                WHERE created_at >= ? AND cove_verification_rounds IS NOT NULL
            """, (cutoff,))
            avg_rounds = cursor.fetchone()[0]

            if avg_rounds is not None:
                metrics.append("# HELP reflexio_cove_avg_verification_rounds_24h Average verification rounds (last 24h)")
                metrics.append("# TYPE reflexio_cove_avg_verification_rounds_24h gauge")
                metrics.append(f"reflexio_cove_avg_verification_rounds_24h {avg_rounds:.2f}")

            conn.close()

        except Exception as e:
            logger.error(f"cove_metrics_collection_failed: {e}")

        return metrics

    def _collect_fact_metrics(self) -> List[str]:
        """Fact extraction quality метрики."""
        metrics = []

        if not self.db_path.exists():
            return metrics

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Hallucination rate (last 24h)
            cutoff = datetime.now() - timedelta(hours=24)
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_hallucination = 1 THEN 1 ELSE 0 END) as hallucinations
                FROM facts
                WHERE created_at >= ?
            """, (cutoff,))
            row = cursor.fetchone()
            total, hallucinations = row[0], row[1] or 0

            if total > 0:
                hallucination_rate = hallucinations / total
                metrics.append("# HELP reflexio_hallucination_rate_24h Hallucination rate (last 24h)")
                metrics.append("# TYPE reflexio_hallucination_rate_24h gauge")
                metrics.append(f"reflexio_hallucination_rate_24h {hallucination_rate:.4f}")

            # Citation coverage (last 24h)
            cursor.execute("""
                SELECT AVG(citation_coverage)
                FROM facts
                WHERE created_at >= ? AND citation_coverage IS NOT NULL
            """, (cutoff,))
            avg_citation = cursor.fetchone()[0]

            if avg_citation is not None:
                metrics.append("# HELP reflexio_citation_coverage_24h Average citation coverage (last 24h)")
                metrics.append("# TYPE reflexio_citation_coverage_24h gauge")
                metrics.append(f"reflexio_citation_coverage_24h {avg_citation:.4f}")

            # Atomicity violations (last 24h)
            cursor.execute("""
                SELECT COUNT(*)
                FROM facts
                WHERE created_at >= ? AND is_atomic = 0
            """, (cutoff,))
            atomicity_violations = cursor.fetchone()[0]

            metrics.append("# HELP reflexio_atomicity_violations_24h Atomicity violations (last 24h)")
            metrics.append("# TYPE reflexio_atomicity_violations_24h counter")
            metrics.append(f"reflexio_atomicity_violations_24h {atomicity_violations}")

            conn.close()

        except Exception as e:
            logger.error(f"fact_metrics_collection_failed: {e}")

        return metrics

    def _collect_retention_metrics(self) -> List[str]:
        """Retention operations метрики (из audit log)."""
        metrics = []

        if not self.db_path.exists():
            return metrics

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Check if audit table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='retention_audit_log'
            """)
            if not cursor.fetchone():
                conn.close()
                return metrics

            # Total retention operations (last 7 days)
            cutoff = datetime.now() - timedelta(days=7)
            cursor.execute("""
                SELECT COUNT(*)
                FROM retention_audit_log
                WHERE executed_at >= ?
            """, (cutoff,))
            total_ops = cursor.fetchone()[0]

            metrics.append("# HELP reflexio_retention_operations_7d Total retention operations (last 7d)")
            metrics.append("# TYPE reflexio_retention_operations_7d counter")
            metrics.append(f"reflexio_retention_operations_7d {total_ops}")

            # Total deleted records (last 7 days)
            cursor.execute("""
                SELECT SUM(record_count)
                FROM retention_audit_log
                WHERE executed_at >= ? AND dry_run = 0
            """, (cutoff,))
            deleted_records = cursor.fetchone()[0] or 0

            metrics.append("# HELP reflexio_retention_deleted_records_7d Total deleted records (last 7d)")
            metrics.append("# TYPE reflexio_retention_deleted_records_7d counter")
            metrics.append(f"reflexio_retention_deleted_records_7d {deleted_records}")

            # Retention errors (last 7 days)
            cursor.execute("""
                SELECT COUNT(*)
                FROM retention_audit_log
                WHERE executed_at >= ? AND error_message IS NOT NULL
            """, (cutoff,))
            errors = cursor.fetchone()[0]

            metrics.append("# HELP reflexio_retention_errors_7d Retention errors (last 7d)")
            metrics.append("# TYPE reflexio_retention_errors_7d counter")
            metrics.append(f"reflexio_retention_errors_7d {errors}")

            conn.close()

        except Exception as e:
            logger.error(f"retention_metrics_collection_failed: {e}")

        return metrics

    def _collect_process_lock_metrics(self) -> List[str]:
        """ProcessLock метрики (из логов или file-based)."""
        metrics = []

        # ProcessLock directory
        lock_dir = Path("/tmp/reflexio_locks") if not Path("C:/").exists() else Path("C:/tmp/reflexio_locks")

        if not lock_dir.exists():
            return metrics

        try:
            # Active locks count
            active_locks = list(lock_dir.glob("*.lock"))
            metrics.append("# HELP reflexio_active_locks Active process locks")
            metrics.append("# TYPE reflexio_active_locks gauge")
            metrics.append(f"reflexio_active_locks {len(active_locks)}")

            # Stale locks (older than 1 hour)
            stale_threshold = datetime.now().timestamp() - 3600
            stale_locks = [
                lock for lock in active_locks
                if lock.stat().st_mtime < stale_threshold
            ]

            metrics.append("# HELP reflexio_stale_locks Stale process locks (>1h old)")
            metrics.append("# TYPE reflexio_stale_locks gauge")
            metrics.append(f"reflexio_stale_locks {len(stale_locks)}")

        except Exception as e:
            logger.error(f"process_lock_metrics_collection_failed: {e}")

        return metrics


def get_prometheus_metrics() -> str:
    """Convenience function для получения метрик.

    Returns:
        Prometheus exposition format string
    """
    collector = PrometheusMetrics()
    return collector.collect_all_metrics()
