"""
Few-Shot Actions — генерация структурированного вывода с примерами.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import List, Dict, Any, Optional
import json

from src.utils.logging import get_logger
from src.llm.providers import get_llm_client
from src.summarizer.prompts import get_few_shot_actions_prompt

logger = get_logger("summarizer.few_shot")


# Примеры для few-shot learning
DEFAULT_EXAMPLES = [
    {
        "action": "summarize",
        "output": {
            "summary": "Краткое саммари текста с ключевыми моментами",
            "key_points": ["пункт 1", "пункт 2", "пункт 3"],
            "sentiment": "neutral",
            "topics": ["тема 1", "тема 2"],
        }
    },
    {
        "action": "extract_tasks",
        "output": {
            "tasks": [
                {
                    "task": "Описание задачи",
                    "priority": "high",
                    "deadline": "2025-11-10",
                    "assignee": None,
                }
            ],
            "total_tasks": 1,
        }
    },
    {
        "action": "analyze_emotions",
        "output": {
            "emotions": ["радость", "уверенность"],
            "intensity": 0.7,
            "dominant_emotion": "радость",
        }
    }
]


def generate_structured_output(
    text: str,
    action_type: str = "summarize",
    examples: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Генерирует структурированный вывод через Few-Shot Actions.
    
    Args:
        text: Исходный текст
        action_type: Тип действия (summarize, extract_tasks, analyze_emotions, etc.)
        examples: Кастомные примеры (если None, используются DEFAULT_EXAMPLES)
        model: Модель LLM (если None, используется из конфигурации)
        
    Returns:
        {
            "action": str,
            "output": Dict,
            "confidence": float,
        }
    """
    logger.info("generating_structured_output", action_type=action_type, text_length=len(text))
    
    if examples is None:
        examples = DEFAULT_EXAMPLES
    
    # Фильтруем примеры по типу действия, если нужно
    relevant_examples = [ex for ex in examples if ex.get("action") == action_type]
    if not relevant_examples:
        relevant_examples = examples[:3]  # Берём первые 3
    
    client = get_llm_client(role="actor")
    if not client:
        logger.error("llm_client_not_available")
        return {
            "action": action_type,
            "output": {},
            "confidence": 0.0,
            "error": "LLM client not available",
        }
    
    # Если указана модель, обновляем клиент
    if model:
        from src.llm.providers import OpenAIClient, AnthropicClient, GoogleGeminiClient
        import os
        
        if model.startswith("gpt") or model.startswith("o1"):
            client = OpenAIClient(model=model)
        elif model.startswith("claude"):
            client = AnthropicClient(model=model)
        elif model.startswith("gemini"):
            client = GoogleGeminiClient(model=model)
    
    prompt = get_few_shot_actions_prompt(text, examples=relevant_examples)
    
    # Добавляем инструкцию для конкретного типа действия
    prompt += f"\n\nТип действия: {action_type}\nСоздай структурированный вывод для этого типа действия."
    
    response = client.call(prompt, system_prompt="Ты — AI-ассистент для анализа текста и генерации структурированного вывода.")
    
    if response.get("error"):
        logger.error("few_shot_generation_failed", error=response["error"])
        return {
            "action": action_type,
            "output": {},
            "confidence": 0.0,
            "error": response["error"],
        }
    
    try:
        # Парсим JSON ответ
        result_text = response["text"]
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(result_text)
        
        # Валидация структуры
        if "action" not in result:
            result["action"] = action_type
        if "output" not in result:
            result["output"] = {}
        if "confidence" not in result:
            result["confidence"] = 0.8  # Default confidence
        
        logger.info("few_shot_generation_complete", action_type=action_type, confidence=result.get("confidence", 0.0))
        
        return result
        
    except json.JSONDecodeError as e:
        logger.warning("few_shot_json_parse_failed", error=str(e))
        # Пробуем извлечь структуру из текста
        return {
            "action": action_type,
            "output": {"raw_text": response["text"]},
            "confidence": 0.5,
            "warning": "JSON parsing failed, returning raw text",
        }


def extract_tasks(text: str, model: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Извлекает задачи из текста.
    
    Returns:
        Список задач с полями: task, priority, deadline, assignee
    """
    result = generate_structured_output(text, action_type="extract_tasks", model=model)
    return result.get("output", {}).get("tasks", [])


def analyze_emotions(text: str, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Анализирует эмоции в тексте.
    
    Returns:
        Словарь с emotions, intensity, dominant_emotion
    """
    result = generate_structured_output(text, action_type="analyze_emotions", model=model)
    return result.get("output", {})





