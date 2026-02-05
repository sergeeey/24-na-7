"""
Critic — валидация и оценка качества саммари с DeepConf.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import Dict, Any, Optional

from src.utils.logging import get_logger
from src.summarizer.deepconf import calculate_confidence_score, should_refine
from src.summarizer.refiner import refine_summary

logger = get_logger("summarizer.critic")


def validate_summary(
    summary: str,
    original_text: str,
    confidence_threshold: float = 0.85,
    auto_refine: bool = True,
) -> Dict[str, Any]:
    """
    Валидирует саммари через DeepConf и при необходимости улучшает.
    
    Args:
        summary: Сгенерированное саммари
        original_text: Исходный текст
        confidence_threshold: Порог confidence для запуска refiner
        auto_refine: Автоматически улучшать при низком confidence
        
    Returns:
        {
            "summary": str,  # Финальное саммари (возможно улучшенное)
            "confidence_score": float,
            "token_entropy": float,
            "metrics": Dict,
            "refined": bool,
            "refinement_reason": Optional[str],
        }
    """
    logger.info("validating_summary", summary_length=len(summary))
    
    # Рассчитываем DeepConf метрики
    metrics = calculate_confidence_score(summary, original_text, use_llm=True)
    confidence = metrics["confidence_score"]
    token_entropy = metrics["token_entropy"]
    
    result = {
        "summary": summary,
        "confidence_score": confidence,
        "token_entropy": token_entropy,
        "metrics": metrics,
        "refined": False,
        "refinement_reason": None,
    }
    
    # Проверяем, нужно ли улучшать
    if should_refine(confidence, confidence_threshold) and auto_refine:
        logger.info("refining_summary", confidence=confidence, threshold=confidence_threshold)
        
        try:
            refined_summary = refine_summary(summary, original_text)
            
            # Пересчитываем метрики для улучшенного саммари
            refined_metrics = calculate_confidence_score(refined_summary, original_text, use_llm=True)
            refined_confidence = refined_metrics["confidence_score"]
            
            # Используем улучшенное саммари, если оно лучше
            if refined_confidence > confidence:
                result["summary"] = refined_summary
                result["confidence_score"] = refined_confidence
                result["token_entropy"] = refined_metrics["token_entropy"]
                result["metrics"] = refined_metrics
                result["refined"] = True
                result["refinement_reason"] = f"Confidence improved: {confidence:.2f} → {refined_confidence:.2f}"
                
                logger.info(
                    "summary_refined",
                    old_confidence=confidence,
                    new_confidence=refined_confidence,
                )
            else:
                result["refinement_reason"] = f"Refinement did not improve confidence: {refined_confidence:.2f} <= {confidence:.2f}"
                
        except Exception as e:
            logger.error("refinement_failed", error=str(e))
            result["refinement_reason"] = f"Refinement failed: {str(e)}"
    
    return result





