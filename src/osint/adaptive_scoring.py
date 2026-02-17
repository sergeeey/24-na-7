"""
Adaptive Mission Scoring — система адаптивных оценок миссий.

Вычисляет вес миссий по достоверности и приоритеты для обновления.
"""
import json
import math
from typing import List, Dict, Any
from pathlib import Path

from src.osint.schemas import MissionResult

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.scoring")
except Exception:
    import logging
    logger = logging.getLogger("osint.scoring")


def calculate_mission_score(result: MissionResult) -> float:
    """
    Вычисляет адаптивный балл миссии.
    
    Формула: mean(confidence) * log(validated_claims + 1)
    
    Args:
        result: Результат выполнения миссии
        
    Returns:
        Балл миссии (0-10)
    """
    if result.total_claims == 0:
        return 0.0
    
    # Средняя уверенность
    mean_confidence = result.avg_confidence
    
    # Логарифмический вес от количества валидированных утверждений
    validated_weight = math.log(result.validated_claims + 1)
    
    # Балл миссии
    score = mean_confidence * validated_weight
    
    # Нормализуем к шкале 0-10
    normalized_score = min(10.0, score * 2)  # Примерная нормализация
    
    logger.debug(
        "mission_score_calculated",
        mission_id=result.mission_id,
        score=normalized_score,
        mean_confidence=mean_confidence,
        validated_weight=validated_weight,
    )
    
    return normalized_score


def calculate_claim_reliability(claim: Dict[str, Any]) -> float:
    """
    Вычисляет надёжность отдельного утверждения.
    
    Учитывает:
    - Калиброванная уверенность
    - Статус валидации
    - Количество источников
    
    Args:
        claim: Утверждение (ValidatedClaim в виде dict)
        
    Returns:
        Надёжность (0-1)
    """
    confidence = claim.get("calibrated_confidence", 0.5)
    status = claim.get("validation_status", "uncertain")
    evidence_count = len(claim.get("evidence", []))
    
    # Множители по статусу
    status_multipliers = {
        "supported": 1.0,
        "uncertain": 0.6,
        "refuted": 0.0,
    }
    
    status_mult = status_multipliers.get(status, 0.5)
    
    # Бонус за множественные источники
    source_bonus = min(0.2, evidence_count * 0.05)
    
    reliability = confidence * status_mult + source_bonus
    
    return min(1.0, reliability)


def prioritize_missions(results: List[MissionResult]) -> List[Dict[str, Any]]:
    """
    Приоритизирует миссии для обновления.
    
    Args:
        results: Список результатов миссий
        
    Returns:
        Отсортированный список миссий с приоритетами
    """
    prioritized = []
    
    for result in results:
        score = calculate_mission_score(result)
        
        # Определяем приоритет обновления
        # Низкий балл = высокий приоритет для обновления
        update_priority = 1.0 / (score + 0.1)  # Избегаем деления на 0
        
        prioritized.append({
            "mission_id": result.mission_id,
            "score": score,
            "update_priority": update_priority,
            "avg_confidence": result.avg_confidence,
            "validated_claims": result.validated_claims,
            "total_claims": result.total_claims,
            "completed_at": result.completed_at,
        })
    
    # Сортируем по приоритету обновления (высокий приоритет = низкий балл)
    prioritized.sort(key=lambda x: x["update_priority"], reverse=True)
    
    return prioritized


def analyze_knowledge_health(results_dir: Path = Path(".cursor/osint/results")) -> Dict[str, Any]:
    """
    Анализирует здоровье базы знаний на основе результатов миссий.
    
    Args:
        results_dir: Директория с результатами миссий
        
    Returns:
        Отчёт о здоровье знаний
    """
    health_report = {
        "total_missions": 0,
        "total_claims": 0,
        "validated_claims": 0,
        "avg_confidence": 0.0,
        "missions_below_threshold": 0,
        "needs_update": [],
    }
    
    if not results_dir.exists():
        logger.warning("results_dir_not_found", path=str(results_dir))
        return health_report
    
    results = []
    
    # Загружаем все результаты миссий
    for result_file in results_dir.glob("*_result_*.json"):
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Конвертируем в MissionResult
            result = MissionResult(**data)
            results.append(result)
            
            health_report["total_missions"] += 1
            health_report["total_claims"] += result.total_claims
            health_report["validated_claims"] += result.validated_claims
            
        except Exception as e:
            logger.warning("result_load_failed", file=str(result_file), error=str(e))
    
    if not results:
        return health_report
    
    # Вычисляем среднюю уверенность
    total_confidence = sum(r.avg_confidence for r in results)
    health_report["avg_confidence"] = total_confidence / len(results)
    
    # Находим миссии ниже порога
    threshold = 0.8
    health_report["missions_below_threshold"] = sum(
        1 for r in results if r.avg_confidence < threshold
    )
    
    # Приоритизируем для обновления
    prioritized = prioritize_missions(results)
    health_report["needs_update"] = [
        m for m in prioritized[:5] if m["avg_confidence"] < threshold
    ]
    
    logger.info(
        "knowledge_health_analyzed",
        missions=health_report["total_missions"],
        avg_confidence=health_report["avg_confidence"],
        needs_update=len(health_report["needs_update"]),
    )
    
    return health_report


def main():
    """CLI для анализа здоровья знаний."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Adaptive Mission Scoring")
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Проанализировать здоровье знаний",
    )
    
    args = parser.parse_args()
    
    if args.analyze:
        health = analyze_knowledge_health()
        
        print("\n" + "=" * 70)
        print("Knowledge Health Analysis")
        print("=" * 70)
        print(f"Total missions: {health['total_missions']}")
        print(f"Total claims: {health['total_claims']}")
        print(f"Validated claims: {health['validated_claims']}")
        print(f"Average confidence: {health['avg_confidence']:.2f}")
        print(f"Missions below threshold: {health['missions_below_threshold']}")
        print()
        
        if health["needs_update"]:
            print("Missions needing update (priority order):")
            for idx, mission in enumerate(health["needs_update"], 1):
                print(f"{idx}. {mission['mission_id']} (score: {mission['score']:.2f}, confidence: {mission['avg_confidence']:.2f})")
        
        print("=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())













