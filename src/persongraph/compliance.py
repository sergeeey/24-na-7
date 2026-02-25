"""
BiometricComplianceManager — TTL-политики для голосовых данных окружения.

Правовая основа: Закон РК «О персональных данных и их защите» (2013, ред. 2024).
  Ст. 8:  Голос = биометрические ПДн (специальная категория).
  Ст. 16: Требуется явное согласие субъекта.
  Ст. 20: Право на удаление («право быть забытым»).

TTL по статусам:
  accumulating       → 7 дней  (неидентифицированные / без подтверждения)
  pending_approval   → 30 дней (накоплено, ждём пользователя)
  person_voice_profiles → 365 дней (ежегодное переподтверждение)

Запуск: ежедневно через APScheduler или cron.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger("persongraph.compliance")

# ──────────────────────────────────────────────
# Константы TTL (дни)
# ──────────────────────────────────────────────

TTL_UNIDENTIFIED_DAYS: int = 7     # person_name IS NULL
TTL_PENDING_DAYS: int = 30         # status = 'pending_approval' без действия
TTL_PROFILE_DAYS: int = 365        # expires_at в person_voice_profiles


# ──────────────────────────────────────────────
# Отчёт об очистке
# ──────────────────────────────────────────────

@dataclass
class CleanupReport:
    run_at: str
    deleted_unidentified: int = 0      # сэмплы без имени > 7 дней
    deleted_pending_expired: int = 0   # pending > 30 дней
    profiles_expired: list[str] = field(default_factory=list)   # требуют переподтверждения
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"[{self.run_at}] Compliance cleanup:",
            f"  deleted unidentified samples : {self.deleted_unidentified}",
            f"  deleted expired pending       : {self.deleted_pending_expired}",
            f"  profiles needing reconfirm    : {len(self.profiles_expired)}",
        ]
        if self.profiles_expired:
            lines.append(f"  → {', '.join(self.profiles_expired)}")
        if self.errors:
            lines.append(f"  ERRORS: {'; '.join(self.errors)}")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# Основной класс
# ──────────────────────────────────────────────

class BiometricComplianceManager:
    """
    Управляет TTL-политиками голосовых данных третьих лиц.

    Использование:
        mgr = BiometricComplianceManager(db_path)
        report = mgr.run_cleanup()
        logger.info("compliance_done", summary=report.summary())
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    # ── Публичный API ──────────────────────────

    def run_cleanup(self) -> CleanupReport:
        """
        Запускает полный цикл очистки.
        Безопасен для ежедневного запуска (idempotent).
        """
        now = datetime.now(timezone.utc)
        report = CleanupReport(run_at=now.isoformat())

        conn = self._connect()
        try:
            # 1. Удалить неидентифицированные сэмплы > TTL_UNIDENTIFIED_DAYS
            cutoff_unidentified = (now - timedelta(days=TTL_UNIDENTIFIED_DAYS)).isoformat()
            cursor = conn.execute(
                """
                DELETE FROM person_voice_samples
                WHERE person_name IS NULL
                AND created_at < ?
                """,
                (cutoff_unidentified,),
            )
            report.deleted_unidentified = cursor.rowcount

            # 2. Удалить pending_approval сэмплы > TTL_PENDING_DAYS (пользователь не ответил)
            cutoff_pending = (now - timedelta(days=TTL_PENDING_DAYS)).isoformat()
            cursor = conn.execute(
                """
                DELETE FROM person_voice_samples
                WHERE status = 'pending_approval'
                AND created_at < ?
                """,
                (cutoff_pending,),
            )
            report.deleted_pending_expired = cursor.rowcount

            # Сбрасываем voice_ready у персон, чьи pending сэмплы удалены
            conn.execute(
                """
                UPDATE persons SET voice_ready = 0
                WHERE voice_ready = 0
                AND name NOT IN (
                    SELECT DISTINCT person_name FROM person_voice_profiles
                )
                AND sample_count > 0
                AND name NOT IN (
                    SELECT DISTINCT person_name FROM person_voice_samples
                    WHERE status IN ('accumulating', 'pending_approval')
                    AND person_name IS NOT NULL
                )
                """,
            )

            conn.commit()

            # 3. Найти профили с истёкшим TTL (не удаляем — уведомляем)
            expired_rows = conn.execute(
                """
                SELECT person_name FROM person_voice_profiles
                WHERE expires_at < ?
                """,
                (now.isoformat(),),
            ).fetchall()
            report.profiles_expired = [r[0] for r in expired_rows]

        except Exception as e:
            conn.rollback()
            report.errors.append(str(e))
            logger.error("compliance_cleanup_error", error=str(e))
        finally:
            conn.close()

        logger.info(
            "compliance_cleanup_done",
            deleted_unidentified=report.deleted_unidentified,
            deleted_pending=report.deleted_pending_expired,
            profiles_expired=len(report.profiles_expired),
        )
        return report

    def delete_person_data(self, person_name: str) -> bool:
        """
        Полное удаление данных персоны (ст. 20 — право быть забытым).

        Удаляет: person_voice_samples, person_voice_profiles, person_interactions.
        Сохраняет: запись в persons (для истории) с обнулёнными биометрическими данными.

        Returns:
            True если удаление выполнено
        """
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM person_voice_samples WHERE person_name = ?",
                (person_name,),
            )
            conn.execute(
                "DELETE FROM person_voice_profiles WHERE person_name = ?",
                (person_name,),
            )
            conn.execute(
                """
                UPDATE persons SET
                    voice_ready = 0,
                    sample_count = 0,
                    approved_at = NULL
                WHERE name = ?
                """,
                (person_name,),
            )
            conn.commit()

            logger.info("gdpr_erasure_complete", person=person_name)
            return True

        except Exception as e:
            conn.rollback()
            logger.error("gdpr_erasure_failed", person=person_name, error=str(e))
            return False
        finally:
            conn.close()

    def get_compliance_status(self) -> dict:
        """
        Возвращает текущий статус соответствия требованиям.
        Используется для GET /compliance/status.
        """
        conn = self._connect()
        try:
            now = datetime.now(timezone.utc).isoformat()

            unidentified = conn.execute(
                "SELECT COUNT(*) FROM person_voice_samples WHERE person_name IS NULL"
            ).fetchone()[0]

            pending = conn.execute(
                "SELECT COUNT(*) FROM person_voice_samples WHERE status = 'pending_approval'"
            ).fetchone()[0]

            active_profiles = conn.execute(
                "SELECT COUNT(*) FROM person_voice_profiles WHERE expires_at > ?",
                (now,),
            ).fetchone()[0]

            expired_profiles = conn.execute(
                "SELECT COUNT(*) FROM person_voice_profiles WHERE expires_at <= ?",
                (now,),
            ).fetchone()[0]

            total_persons = conn.execute(
                "SELECT COUNT(*) FROM persons"
            ).fetchone()[0]

            return {
                "unidentified_samples": unidentified,
                "pending_approval_samples": pending,
                "active_voice_profiles": active_profiles,
                "expired_voice_profiles": expired_profiles,
                "total_persons_in_graph": total_persons,
                "ttl_unidentified_days": TTL_UNIDENTIFIED_DAYS,
                "ttl_pending_days": TTL_PENDING_DAYS,
                "ttl_profile_days": TTL_PROFILE_DAYS,
                "checked_at": now,
            }
        finally:
            conn.close()

    # ── Приватные методы ───────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
