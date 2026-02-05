"""
Refiner — улучшение саммари через Claude 4.5 при низком confidence.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import Dict, Any, Optional

from src.utils.logging import get_logger
from src.llm.providers import AnthropicClient, OpenAIClient
import os

logger = get_logger("summarizer.refiner")


def refine_summary(
    summary: str,
    original_text: str,
    refiner_model: str = "claude-4-5-sonnet-20241022",
) -> str:
    """
    Улучшает саммари через refiner-модель (Claude 4.5 по умолчанию).
    
    Args:
        summary: Текущее саммари
        original_text: Исходный текст
        refiner_model: Модель для улучшения
        
    Returns:
        Улучшенное саммари
    """
    logger.info("refining_summary", refiner_model=refiner_model)
    
    # Пробуем Claude 4.5
    try:
        client = AnthropicClient(model=refiner_model)
        if client.client:
            prompt = f"""Ты — эксперт по улучшению саммари.

Исходный текст:
{original_text[:2000]}...

Текущее саммари (требует улучшения):
{summary}

Улучши это саммари:
1. Исправь фактические ошибки
2. Добавь недостающие ключевые детали
3. Улучши связность и логику
4. Сохрани краткость

Верни только улучшенное саммари, без дополнительных комментариев.
"""
            response = client.call(prompt, system_prompt="Ты — эксперт по улучшению качества текста.")
            
            if not response.get("error") and response.get("text"):
                logger.info("summary_refined_successfully", model=refiner_model)
                return response["text"]
    except Exception as e:
        logger.warning("anthropic_refiner_failed", error=str(e))
    
    # Fallback на GPT-4o или другую модель
    try:
        fallback_model = os.getenv("REFINER_FALLBACK_MODEL", "gpt-4o")
        client = OpenAIClient(model=fallback_model)
        
        if client.client:
            prompt = f"""Улучши это саммари, исправив ошибки и добавив недостающие детали.

Исходный текст:
{original_text[:2000]}...

Текущее саммари:
{summary}

Улучшенное саммари:
"""
            response = client.call(prompt, system_prompt="Ты — эксперт по улучшению саммари.")
            
            if not response.get("error") and response.get("text"):
                logger.info("summary_refined_with_fallback", model=fallback_model)
                return response["text"]
    except Exception as e:
        logger.error("refiner_fallback_failed", error=str(e))
    
    # Если всё провалилось, возвращаем исходное
    logger.warning("refiner_completely_failed", returning_original=True)
    return summary





