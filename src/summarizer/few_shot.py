"""
Few-Shot Actions — генерация структурированного вывода с примерами.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import List, Dict, Any, Optional
import json

from src.utils.logging import get_logger
from src.llm.providers import get_llm_client
from src.summarizer.prompts import get_few_shot_actions_prompt
from src.llm.schemas.digest import DigestAnalysis, DigestOutput

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
    },
    {
        "action": "analyze_recording",
        "output": {
            "summary": "Одно предложение: о чём запись",
            "emotions": ["эмоция1", "эмоция2"],
            "actions": ["действие 1", "действие 2"],
            "topics": ["тема1", "тема2"],
            "urgency": "high",
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
        
        result_dict = json.loads(result_text)
        
        # Валидация структуры через Pydantic
        try:
            # Убеждаемся что есть обязательные поля
            if "action" not in result_dict:
                result_dict["action"] = action_type
            if "output" not in result_dict:
                result_dict["output"] = {}
            if "confidence" not in result_dict:
                result_dict["confidence"] = 0.8  # Default confidence
            
            # Валидируем через Pydantic схему
            validated = DigestAnalysis(**result_dict)
            
            logger.info(
                "few_shot_generation_complete",
                action_type=validated.action,
                confidence=validated.confidence,
                validated=True
            )
            
            return validated.dict()
            
        except Exception as validation_error:
            logger.warning(
                "few_shot_validation_failed",
                error=str(validation_error),
                raw_result=result_dict
            )
            # Fallback: возвращаем с предупреждением
            return {
                "action": action_type,
                "output": result_dict.get("output", {}),
                "confidence": result_dict.get("confidence", 0.5),
                "warning": f"Validation failed: {str(validation_error)}",
            }
        
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


def analyze_recording_text(text: str, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Анализирует запись голоса: саммари, эмоции, действия, темы, срочность.
    Phase 2 — формат из ROADMAP.
    
    Returns:
        Словарь с summary, emotions (list), actions (list), topics (list), urgency (low/medium/high)
    """
    if not (text or "").strip():
        return {
            "summary": "",
            "emotions": [],
            "actions": [],
            "topics": [],
            "urgency": "medium",
        }
    result = generate_structured_output(text, action_type="analyze_recording", model=model)
    out = result.get("output", {})
    return {
        "summary": out.get("summary") or "",
        "emotions": out.get("emotions") if isinstance(out.get("emotions"), list) else [],
        "actions": out.get("actions") if isinstance(out.get("actions"), list) else [],
        "topics": out.get("topics") if isinstance(out.get("topics"), list) else [],
        "urgency": out.get("urgency") if out.get("urgency") in ("low", "medium", "high") else "medium",
    }





