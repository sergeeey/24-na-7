"""
Compliance API — управление биометрическими данными третьих лиц.

Правовая основа: Закон РК «О персональных данных» (2013, ред. 2024).
  Ст. 8:  Голос = биометрические ПДн (спец. категория).
  Ст. 20: Право на удаление («право быть забытым»).

Endpoints:
  GET  /compliance/status                — текущее состояние TTL политик
  DELETE /compliance/erase/{person}      — полное удаление данных персоны
  POST /compliance/run-cleanup           — ручной запуск TTL-очистки (admin)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.persongraph.compliance import BiometricComplianceManager
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api.compliance")
router = APIRouter(prefix="/compliance", tags=["compliance"])


# ──────────────────────────────────────────────
# Схемы ответов
# ──────────────────────────────────────────────


class ComplianceStatusOut(BaseModel):
    unidentified_samples: int
    pending_approval_samples: int
    active_voice_profiles: int
    expired_voice_profiles: int
    total_persons_in_graph: int
    ttl_unidentified_days: int
    ttl_pending_days: int
    ttl_profile_days: int
    checked_at: str


class CleanupResultOut(BaseModel):
    run_at: str
    deleted_unidentified: int
    deleted_pending_expired: int
    profiles_needing_reconfirm: list[str]
    errors: list[str]


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.get("/status", response_model=ComplianceStatusOut)
async def compliance_status():
    """
    Возвращает текущий статус соответствия требованиям KZ GDPR.

    Показывает сколько неидентифицированных сэмплов, ожидающих подтверждения
    и истёкших профилей есть в системе.
    """
    db_path = settings.STORAGE_PATH / "reflexio.db"
    mgr = BiometricComplianceManager(db_path)
    status = mgr.get_compliance_status()
    return ComplianceStatusOut(**status)


@router.delete("/erase/{person_name}")
async def erase_person(person_name: str):
    """
    Полное удаление биометрических данных персоны (ст. 20 ЗРК).

    Удаляет: голосовые сэмплы, профиль, историю взаимодействий.
    Сохраняет: только имя персоны в таблице persons (для истории).

    Необратимо. Требует явного запроса.
    """
    db_path = settings.STORAGE_PATH / "reflexio.db"
    mgr = BiometricComplianceManager(db_path)
    ok = mgr.delete_person_data(person_name)
    if not ok:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to erase data for '{person_name}'",
        )
    logger.info("gdpr_erase_api", person=person_name)
    return {
        "status": "erased",
        "person": person_name,
        "detail": "All biometric data deleted per KZ GDPR art.20",
    }


@router.post("/run-cleanup", response_model=CleanupResultOut)
async def run_cleanup():
    """
    Ручной запуск TTL-очистки.

    Обычно запускается автоматически APScheduler в 03:00.
    Используйте для немедленной очистки или тестирования.

    Idempotent — безопасно запускать несколько раз.
    """
    db_path = settings.STORAGE_PATH / "reflexio.db"
    mgr = BiometricComplianceManager(db_path)
    report = mgr.run_cleanup()

    logger.info(
        "compliance_manual_cleanup",
        deleted_unidentified=report.deleted_unidentified,
        deleted_pending=report.deleted_pending_expired,
    )

    return CleanupResultOut(
        run_at=report.run_at,
        deleted_unidentified=report.deleted_unidentified,
        deleted_pending_expired=report.deleted_pending_expired,
        profiles_needing_reconfirm=report.profiles_expired,
        errors=report.errors,
    )
