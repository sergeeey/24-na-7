"""
Data Quality (DQ) Metrics для Memory Bank.

Реализует измерение качества данных: Accuracy, Completeness, Timeliness, Consistency, Validity.
"""
from typing import List, Dict, Any
from datetime import datetime, timezone

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.dq")
except Exception:
    import logging
    logger = logging.getLogger("osint.dq")


def calculate_accuracy(claims: List[Dict[str, Any]]) -> float:
    """
    Вычисляет Accuracy — точность утверждений.
    
    Accuracy = (supported claims) / (total claims)
    
    Args:
        claims: Список утверждений с validation_status
        
    Returns:
        Accuracy score (0.0-1.0)
    """
    if not claims:
        return 0.0
    
    supported = sum(1 for c in claims if c.get("status") == "supported")
    total = len(claims)
    
    accuracy = supported / total if total > 0 else 0.0
    
    logger.debug("dq_accuracy_calculated", accuracy=accuracy, supported=supported, total=total)
    
    return accuracy


def calculate_completeness(claims: List[Dict[str, Any]]) -> float:
    """
    Вычисляет Completeness — полноту данных.
    
    Completeness = (claims with sources) / (total claims)
    
    Args:
        claims: Список утверждений с source_urls или sources
        
    Returns:
        Completeness score (0.0-1.0)
    """
    if not claims:
        return 0.0
    
    with_sources = sum(
        1 for c in claims
        if (c.get("sources") and len(c.get("sources", [])) > 0) or
           (c.get("source_urls") and len(c.get("source_urls", [])) > 0)
    )
    total = len(claims)
    
    completeness = with_sources / total if total > 0 else 0.0
    
    logger.debug("dq_completeness_calculated", completeness=completeness, with_sources=with_sources, total=total)
    
    return completeness


def calculate_timeliness(claims: List[Dict[str, Any]], max_age_days: int = 30) -> float:
    """
    Вычисляет Timeliness — актуальность данных.
    
    Timeliness = (fresh claims) / (total claims)
    
    Args:
        claims: Список утверждений с метаданными о дате
        max_age_days: Максимальный возраст в днях для "свежих" данных
        
    Returns:
        Timeliness score (0.0-1.0)
    """
    if not claims:
        return 0.0
    
    now = datetime.now(timezone.utc)
    fresh_count = 0
    
    for claim in claims:
        # Пытаемся найти дату в различных форматах
        date_str = (
            claim.get("extracted_at") or
            claim.get("validated_at") or
            claim.get("scraped_at") or
            claim.get("date")
        )
        
        if date_str:
            try:
                if isinstance(date_str, str):
                    # Парсим ISO формат
                    if "T" in date_str:
                        claim_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    else:
                        claim_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                else:
                    claim_date = date_str
                
                age_days = (now - claim_date).days
                if age_days <= max_age_days:
                    fresh_count += 1
            except Exception:
                # Если не удалось распарсить дату, считаем устаревшим
                pass
        else:
            # Если даты нет, считаем устаревшим
            pass
    
    total = len(claims)
    timeliness = fresh_count / total if total > 0 else 0.0
    
    logger.debug("dq_timeliness_calculated", timeliness=timeliness, fresh_count=fresh_count, total=total)
    
    return timeliness


def calculate_consistency(claims: List[Dict[str, Any]]) -> float:
    """
    Вычисляет Consistency — согласованность данных.
    
    Consistency = 1 - (contradicting claims) / (total claims)
    
    Упрощённая метрика: проверяем наличие противоречащих утверждений
    (supported vs refuted для похожих текстов).
    
    Args:
        claims: Список утверждений
        
    Returns:
        Consistency score (0.0-1.0)
    """
    if not claims:
        return 1.0
    
    # Простая эвристика: если есть supported и refuted для похожих текстов
    # (проверяем первые 50 символов на схожесть)
    contradictions = 0
    
    for i, claim1 in enumerate(claims):
        text1_prefix = claim1.get("text", "")[:50].lower()
        status1 = claim1.get("status")
        
        for claim2 in claims[i+1:]:
            text2_prefix = claim2.get("text", "")[:50].lower()
            status2 = claim2.get("status")
            
            # Если тексты похожи, но статусы противоречат
            if text1_prefix == text2_prefix or (len(text1_prefix) > 20 and text1_prefix in text2_prefix):
                if (status1 == "supported" and status2 == "refuted") or \
                   (status1 == "refuted" and status2 == "supported"):
                    contradictions += 1
                    break
    
    total = len(claims)
    consistency = 1.0 - (contradictions / total) if total > 0 else 1.0
    
    logger.debug("dq_consistency_calculated", consistency=consistency, contradictions=contradictions, total=total)
    
    return max(0.0, consistency)  # Не может быть отрицательным


def calculate_validity(claims: List[Dict[str, Any]]) -> float:
    """
    Вычисляет Validity — валидность данных.
    
    Validity = (claims with valid structure) / (total claims)
    
    Проверяет наличие обязательных полей: text, status, confidence.
    
    Args:
        claims: Список утверждений
        
    Returns:
        Validity score (0.0-1.0)
    """
    if not claims:
        return 0.0
    
    valid_count = 0
    
    for claim in claims:
        has_text = bool(claim.get("text"))
        has_status = claim.get("status") in ["supported", "refuted", "uncertain"]
        has_confidence = "confidence" in claim and 0.0 <= claim.get("confidence", 0) <= 1.0
        
        if has_text and has_status and has_confidence:
            valid_count += 1
    
    total = len(claims)
    validity = valid_count / total if total > 0 else 0.0
    
    logger.debug("dq_validity_calculated", validity=validity, valid_count=valid_count, total=total)
    
    return validity


def calculate_dq_metrics(claims: List[Dict[str, Any]], max_age_days: int = 30) -> Dict[str, float]:
    """
    Вычисляет все DQ метрики для списка утверждений.
    
    Args:
        claims: Список утверждений
        max_age_days: Максимальный возраст для Timeliness
        
    Returns:
        Словарь с DQ метриками
    """
    metrics = {
        "accuracy": calculate_accuracy(claims),
        "completeness": calculate_completeness(claims),
        "timeliness": calculate_timeliness(claims, max_age_days),
        "consistency": calculate_consistency(claims),
        "validity": calculate_validity(claims),
    }
    
    # Общая DQ оценка (среднее арифметическое с весами)
    weights = {
        "accuracy": 0.3,
        "completeness": 0.2,
        "timeliness": 0.2,
        "consistency": 0.15,
        "validity": 0.15,
    }
    
    overall_dq = sum(metrics[key] * weights[key] for key in metrics.keys())
    metrics["overall_dq_score"] = overall_dq
    
    logger.info("dq_metrics_calculated", metrics=metrics, claims_count=len(claims))
    
    return metrics













