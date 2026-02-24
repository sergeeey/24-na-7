"""
Chain of Density (CoD) — постепенное уплотнение саммари.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import Dict, Any, Optional
import json

from src.utils.logging import get_logger
from src.llm.providers import get_llm_client
from src.summarizer.prompts import get_chain_of_density_prompt

logger = get_logger("summarizer.cod")


def generate_dense_summary(
    text: str,
    iterations: int = 5,
    model: Optional[str] = None,
    include_emotions: bool = True,
) -> Dict[str, Any]:
    """
    Генерирует информационно-плотное саммари через Chain of Density.
    
    Args:
        text: Исходный текст
        iterations: Количество итераций уплотнения
        model: Модель LLM (если None, используется из конфигурации)
        
    Returns:
        {
            "summary": str,
            "density_score": float,
            "iterations": List[Dict],
            "entities": List[str],
            "key_facts": List[str],
        }
    """
    logger.info("generating_dense_summary", text_length=len(text), iterations=iterations, include_emotions=include_emotions)
    
    # Анализируем эмоции если нужно
    emotions_context = ""
    if include_emotions:
        try:
            from src.summarizer.emotion_analysis import analyze_emotions
            emotions_result = analyze_emotions(text)
            if emotions_result.get("emotions"):
                emotions_context = f"\n\nЭмоциональный контекст: {', '.join(emotions_result.get('emotions', []))} (интенсивность: {emotions_result.get('intensity', 0.0):.2f}, sentiment: {emotions_result.get('sentiment', 'neutral')})"
                logger.info("emotions_analyzed", emotions=emotions_result.get("emotions"))
        except Exception as e:
            logger.warning("emotion_analysis_failed", error=str(e))
    
    client = get_llm_client(role="actor")
    if not client:
        logger.error("llm_client_not_available")
        return {
            "summary": "",
            "density_score": 0.0,
            "iterations": [],
            "error": "LLM client not available",
        }
    
    # Если указана модель, обновляем клиент
    if model:
        from src.llm.providers import OpenAIClient, AnthropicClient
        
        if model.startswith("gpt") or model.startswith("o1"):
            client = OpenAIClient(model=model)
        elif model.startswith("claude"):
            client = AnthropicClient(model=model)
    
    iterations_results = []
    current_summary = ""
    
    for i in range(iterations):
        prompt = get_chain_of_density_prompt(text, iterations=iterations)
        
        # Добавляем эмоциональный контекст
        if emotions_context:
            prompt += emotions_context
        
        if i > 0:
            prompt += f"\n\nТекущее саммари (итерация {i}):\n{current_summary}\n\nУплотни это саммари, добавив конкретные детали и учитывая эмоциональный контекст."
        
        response = client.call(prompt, system_prompt="Ты — эксперт по созданию информационно-плотных саммари.")
        
        if response.get("error"):
            logger.error("cod_iteration_failed", iteration=i, error=response["error"])
            break
        
        try:
            # ПОЧЕМУ: LLM может вернуть JSON в разных обёртках:
            # 1. ```json ... ```  2. ```...```  3. Итерация N:\n{...}  4. Просто {..}
            # Ищем первый валидный JSON-объект в ответе.
            result_text = response["text"]
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            # Если не JSON — ищем последний {...} блок (самая плотная итерация)
            result = None
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                # Ищем все JSON-объекты в тексте
                import re
                json_blocks = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result_text)
                for block in reversed(json_blocks):  # берём последний (самый плотный)
                    try:
                        result = json.loads(block)
                        if "summary" in result:
                            break
                    except json.JSONDecodeError:
                        continue

            if not result or "summary" not in result:
                raise json.JSONDecodeError("No valid JSON with 'summary' key found", result_text, 0)
            current_summary = result.get("summary", current_summary)
            
            iterations_results.append({
                "iteration": i + 1,
                "summary": current_summary,
                "density_score": result.get("density_score", 0.0),
                "entities": result.get("entities", []),
                "key_facts": result.get("key_facts", []),
            })
            
            logger.info(
                "cod_iteration_complete",
                iteration=i + 1,
                density_score=result.get("density_score", 0.0),
            )
            
        except json.JSONDecodeError as e:
            logger.warning("cod_json_parse_failed", iteration=i, error=str(e))
            # Используем текст как есть
            current_summary = response["text"]
            iterations_results.append({
                "iteration": i + 1,
                "summary": current_summary,
                "density_score": 0.0,
            })
    
    # Выбираем лучшую итерацию (с максимальным density_score)
    best_iteration = max(iterations_results, key=lambda x: x.get("density_score", 0.0), default={})
    
    return {
        "summary": best_iteration.get("summary", current_summary),
        "density_score": best_iteration.get("density_score", 0.0),
        "iterations": iterations_results,
        "entities": best_iteration.get("entities", []),
        "key_facts": best_iteration.get("key_facts", []),
    }

