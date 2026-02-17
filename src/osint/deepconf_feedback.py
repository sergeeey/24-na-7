"""
DeepConf Feedback Loop — автоматическая реакция на изменения достоверности.

Интегрируется с Governance Loop для самоадаптации на основе метрик DeepConf.
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.feedback")
except Exception:
    import logging
    logger = logging.getLogger("osint.feedback")


def get_current_deepconf_metrics() -> Dict[str, Any]:
    """
    Получает текущие метрики DeepConf из cursor-metrics.json.
    
    Returns:
        Словарь с метриками OSINT/DeepConf
    """
    metrics_file = Path("cursor-metrics.json")
    
    if not metrics_file.exists():
        return {
            "avg_deepconf_confidence": None,
            "missions_completed": 0,
            "validated_claims": 0,
        }
    
    try:
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
        osint_metrics = data.get("metrics", {}).get("osint", {})
        
        return {
            "avg_deepconf_confidence": osint_metrics.get("avg_deepconf_confidence"),
            "missions_completed": osint_metrics.get("missions_completed", 0),
            "validated_claims": osint_metrics.get("validated_claims", 0),
            "total_claims": osint_metrics.get("total_claims", 0),
        }
    except Exception as e:
        logger.error("metrics_load_failed", error=str(e))
        return {
            "avg_deepconf_confidence": None,
            "missions_completed": 0,
            "validated_claims": 0,
        }


def should_trigger_auto_regeneration(avg_confidence: Optional[float], threshold: float = 0.8) -> bool:
    """
    Определяет, нужно ли запустить автоматическую регенерацию миссий.
    
    Args:
        avg_confidence: Средняя уверенность DeepConf
        threshold: Порог для активации
        
    Returns:
        True если нужно запустить регенерацию
    """
    if avg_confidence is None:
        return False
    
    return avg_confidence < threshold


def should_trigger_knowledge_update(avg_confidence: Optional[float], threshold: float = 0.95) -> bool:
    """
    Определяет, нужно ли приоритизировать обновление старых знаний.
    
    Args:
        avg_confidence: Средняя уверенность DeepConf
        threshold: Порог для активации обновления
        
    Returns:
        True если нужно обновить знания
    """
    if avg_confidence is None:
        return False
    
    return avg_confidence >= threshold


def update_governance_profile(
    avg_confidence: Optional[float],
    missions_completed: int,
    knowledge_health: str,
) -> Dict[str, Any]:
    """
    Обновляет профиль Governance с OSINT метриками.
    
    Args:
        avg_confidence: Средняя уверенность DeepConf
        missions_completed: Количество выполненных миссий
        knowledge_health: Состояние базы знаний
        
    Returns:
        Обновлённая секция osint_governance
    """
    from datetime import datetime, timezone
    
    auto_regeneration = False
    knowledge_update = False
    
    if avg_confidence is not None:
        auto_regeneration = should_trigger_auto_regeneration(avg_confidence)
        knowledge_update = should_trigger_knowledge_update(avg_confidence)
    
    return {
        "avg_deepconf_confidence": avg_confidence,
        "missions_completed": missions_completed,
        "knowledge_health": knowledge_health,
        "auto_regeneration_active": auto_regeneration,
        "knowledge_update_priority": knowledge_update,
        "last_update": datetime.now(timezone.utc).isoformat(),
    }


def apply_feedback_loop() -> Dict[str, Any]:
    """
    Применяет DeepConf Feedback Loop.
    
    Проверяет метрики и обновляет Governance профиль.
    
    Returns:
        Результаты применения feedback loop
    """
    logger.info("deepconf_feedback_loop_started")
    
    # Получаем метрики
    metrics = get_current_deepconf_metrics()
    avg_confidence = metrics.get("avg_deepconf_confidence")
    
    # Определяем здоровье знаний
    if avg_confidence is None:
        knowledge_health = "unknown"
    elif avg_confidence >= 0.9:
        knowledge_health = "excellent"
    elif avg_confidence >= 0.8:
        knowledge_health = "good"
    elif avg_confidence >= 0.7:
        knowledge_health = "fair"
    else:
        knowledge_health = "poor"
    
    # Обновляем Governance
    osint_governance = update_governance_profile(
        avg_confidence=avg_confidence,
        missions_completed=metrics.get("missions_completed", 0),
        knowledge_health=knowledge_health,
    )
    
    # Загружаем текущий профиль
    profile_path = Path(".cursor/governance/profile.yaml")
    
    if profile_path.exists():
        try:
            import yaml
            
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = yaml.safe_load(f)
            
            # Обновляем секцию osint_governance
            profile["osint_governance"] = osint_governance
            
            # Сохраняем
            with open(profile_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(profile, f, allow_unicode=True, default_flow_style=False)
            
            logger.info("governance_profile_updated", osint_governance=osint_governance)
            
        except Exception as e:
            logger.error("governance_update_failed", error=str(e))
    
    # Формируем рекомендации
    recommendations = []
    
    if osint_governance["auto_regeneration_active"]:
        recommendations.append(
            "DeepConf confidence below threshold (0.8). Auto-regeneration of missions recommended."
        )
    
    if osint_governance["knowledge_update_priority"]:
        recommendations.append(
            "DeepConf confidence high (≥0.95). Prioritize updating old knowledge."
        )
    
    if knowledge_health == "poor":
        recommendations.append(
            "Knowledge health is poor. Review and revalidate recent missions."
        )
    
    result = {
        "metrics": metrics,
        "knowledge_health": knowledge_health,
        "osint_governance": osint_governance,
        "recommendations": recommendations,
    }
    
    logger.info(
        "deepconf_feedback_loop_completed",
        avg_confidence=avg_confidence,
        health=knowledge_health,
        recommendations_count=len(recommendations),
    )
    
    return result


def main():
    """CLI для DeepConf Feedback Loop."""
    import argparse
    
    parser = argparse.ArgumentParser(description="DeepConf Feedback Loop")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Применить feedback loop и обновить Governance",
    )
    
    args = parser.parse_args()
    
    if args.apply:
        result = apply_feedback_loop()
        
        print("\n" + "=" * 70)
        print("DeepConf Feedback Loop")
        print("=" * 70)
        print(f"Avg DeepConf Confidence: {result['metrics'].get('avg_deepconf_confidence', 'N/A')}")
        print(f"Knowledge Health: {result['knowledge_health']}")
        print(f"Missions Completed: {result['metrics'].get('missions_completed', 0)}")
        print()
        
        if result["recommendations"]:
            print("Recommendations:")
            for rec in result["recommendations"]:
                print(f"  - {rec}")
        else:
            print("No recommendations.")
        
        print("=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())













