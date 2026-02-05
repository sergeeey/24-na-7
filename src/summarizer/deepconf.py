"""
DeepConf — метрики confidence и token entropy для саммари.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import Dict, Any, Optional
import json
import math
from collections import Counter

from src.utils.logging import get_logger
from src.llm.providers import get_llm_client
from src.summarizer.prompts import get_critic_prompt

logger = get_logger("summarizer.deepconf")


def calculate_token_entropy(text: str) -> float:
    """
    Рассчитывает энтропию токенов (мера предсказуемости).
    
    Args:
        text: Текст для анализа
        
    Returns:
        Энтропия (0.0-1.0, где 0 = полностью предсказуемо)
    """
    if not text:
        return 0.0
    
    # Простая токенизация (можно заменить на более сложную)
    tokens = text.lower().split()
    
    if len(tokens) < 2:
        return 0.0
    
    # Подсчитываем частоты
    token_counts = Counter(tokens)
    total_tokens = len(tokens)
    
    # Рассчитываем энтропию Шеннона
    entropy = 0.0
    for count in token_counts.values():
        probability = count / total_tokens
        if probability > 0:
            entropy -= probability * math.log2(probability)
    
    # Нормализуем (максимальная энтропия = log2(unique_tokens))
    max_entropy = math.log2(len(token_counts)) if len(token_counts) > 1 else 1.0
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
    
    return min(normalized_entropy, 1.0)


def calculate_confidence_score(
    summary: str,
    original_text: str,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    Рассчитывает confidence score для саммари через DeepConf.
    
    Args:
        summary: Сгенерированное саммари
        original_text: Исходный текст
        use_llm: Использовать LLM для оценки (иначе только эвристики)
        
    Returns:
        {
            "confidence_score": float,
            "token_entropy": float,
            "factual_consistency": float,
            "completeness": float,
            "coherence": float,
            "conciseness": float,
        }
    """
    logger.info("calculating_confidence_score", summary_length=len(summary))
    
    # Рассчитываем token entropy
    token_entropy = calculate_token_entropy(summary)
    
    # Эвристические метрики
    summary_length = len(summary.split())
    original_length = len(original_text.split())
    compression_ratio = summary_length / original_length if original_length > 0 else 0.0
    
    # Базовые метрики (эвристики)
    base_metrics = {
        "token_entropy": token_entropy,
        "compression_ratio": compression_ratio,
        "factual_consistency": 0.8,  # Placeholder, требует LLM
        "completeness": min(compression_ratio * 2, 1.0),  # Эвристика
        "coherence": 0.8,  # Placeholder
        "conciseness": 1.0 - compression_ratio if compression_ratio < 1.0 else 0.5,
    }
    
    # Если не используем LLM, возвращаем эвристики
    if not use_llm:
        confidence_score = (
            base_metrics["factual_consistency"] * 0.4 +
            base_metrics["completeness"] * 0.2 +
            base_metrics["coherence"] * 0.2 +
            base_metrics["conciseness"] * 0.2
        )
        
        return {
            "confidence_score": confidence_score,
            **base_metrics,
        }
    
    # Используем LLM для оценки
    client = get_llm_client(role="critic")
    if not client:
        logger.warning("llm_critic_not_available", using_heuristics=True)
        return calculate_confidence_score(summary, original_text, use_llm=False)
    
    prompt = get_critic_prompt(summary, original_text)
    response = client.call(prompt, system_prompt="Ты — эксперт по оценке качества саммари.")
    
    if response.get("error"):
        logger.warning("llm_critic_failed", error=response["error"], using_heuristics=True)
        return calculate_confidence_score(summary, original_text, use_llm=False)
    
    try:
        # Парсим JSON ответ
        result_text = response["text"]
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        llm_metrics = json.loads(result_text)
        
        # Объединяем метрики
        confidence_score = (
            llm_metrics.get("factual_consistency", 0.8) * 0.4 +
            llm_metrics.get("completeness", 0.8) * 0.2 +
            llm_metrics.get("coherence", 0.8) * 0.2 +
            llm_metrics.get("conciseness", 0.8) * 0.2
        )
        
        return {
            "confidence_score": confidence_score,
            "token_entropy": token_entropy,
            "factual_consistency": llm_metrics.get("factual_consistency", 0.8),
            "completeness": llm_metrics.get("completeness", 0.8),
            "coherence": llm_metrics.get("coherence", 0.8),
            "conciseness": llm_metrics.get("conciseness", 0.8),
            "issues": llm_metrics.get("issues", []),
            "recommendations": llm_metrics.get("recommendations", []),
        }
        
    except json.JSONDecodeError as e:
        logger.warning("deepconf_json_parse_failed", error=str(e), using_heuristics=True)
        return calculate_confidence_score(summary, original_text, use_llm=False)


def should_refine(confidence_score: float, threshold: float = 0.85) -> bool:
    """
    Определяет, нужно ли улучшать саммари через refiner.
    
    Args:
        confidence_score: Текущий confidence score
        threshold: Порог для запуска refiner
        
    Returns:
        True если нужно улучшать
    """
    return confidence_score < threshold





