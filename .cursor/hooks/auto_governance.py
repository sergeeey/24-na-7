"""
Auto-Governance Hook — автоматическое переключение профилей на основе метрик.

Если ai_reliability_index < 0.8 → запускает build-reflexio для улучшения.
Если audit_score >= 90 → переключает на self-adaptive режим.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("hooks.auto_governance")


def check_and_apply_governance() -> None:
    """Проверяет метрики и применяет governance правила."""
    audit_report = Path(".cursor/audit/audit_report.json")
    
    if not audit_report.exists():
        logger.debug("audit_report_not_found")
        return
    
    try:
        data = json.loads(audit_report.read_text(encoding="utf-8"))
        score = data.get("score", 0)
        reliability = data.get("ai_reliability_index", 0.0)
        level = data.get("level", 0)
        
        logger.info(
            "governance_check",
            score=score,
            reliability=reliability,
            level=level,
        )
        
        # Правило 1: Низкая надёжность → запустить build-reflexio
        if reliability < 0.8 and level >= 2:
            logger.warning(
                "reliability_low",
                reliability=reliability,
                action="triggering_build",
            )
            try:
                # Запускаем сборку для улучшения
                subprocess.run(
                    ["python", ".cursor/playbooks/build-reflexio.yaml"],
                    timeout=600,
                )
            except Exception as e:
                logger.error("build_trigger_failed", error=str(e))
        
        # Правило 2: Высокий балл → переключить профиль
        if score >= 90 and level >= 4:
            logger.info(
                "high_score_achieved",
                score=score,
                action="upgrading_to_self_adaptive",
            )
            # Governance loop автоматически применит профиль
        
        # Правило 3: Если validation errors → блокировать deployment
        validation_result = Path(".cursor/validation/last_result.json")
        if validation_result.exists():
            val_data = json.loads(validation_result.read_text(encoding="utf-8"))
            if val_data.get("total_failed", 0) > 0:
                logger.warning(
                    "validation_errors_detected",
                    errors=val_data["total_failed"],
                    action="deployment_blocked",
                )
        
    except Exception as e:
        logger.error("governance_check_failed", error=str(e))


def main():
    """Точка входа."""
    check_and_apply_governance()


if __name__ == "__main__":
    main()













