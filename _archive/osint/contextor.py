"""
Контекстор 2025 — генерация R.C.T.F. промптов.

Реализует методологию Role-Context-Task-Format для структурированных LLM промптов.
"""
from typing import Dict, Any, Optional
import json
import re

from src.osint.schemas import RCTFContext, Source

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.contextor")
except Exception:
    import logging
    logger = logging.getLogger("osint.contextor")


def build_rctf_prompt(
    role: str,
    context_data: Dict[str, Any],
    task: str,
    format_schema: Dict[str, Any],
    sources: Optional[list[Source]] = None,
) -> str:
    """
    Строит R.C.T.F. промпт для LLM.
    
    Args:
        role: Роль, которую должен принять LLM (например, "research analyst")
        context_data: Контекстные данные (например, метаинформация о запросе)
        task: Конкретная задача для выполнения
        format_schema: Схема формата вывода (JSON schema)
        sources: Опциональные источники информации
        
    Returns:
        Форматированный промпт в формате R.C.T.F.
    """
    prompt_parts = []
    
    # Role
    prompt_parts.append(f"<role>{role}</role>")
    
    # Context
    context_str = json.dumps(context_data, indent=2, ensure_ascii=False) if context_data else "{}"
    prompt_parts.append(f"<context>{context_str}</context>")
    
    # Sources (если есть)
    if sources:
        sources_text = "\n\n".join([
            f"**Source {idx + 1}:** {src.url}\n"
            f"{src.title or 'No title'}\n"
            f"{src.content[:1000] + '...' if src.content and len(src.content) > 1000 else (src.content or 'No content')}"
            for idx, src in enumerate(sources[:10])  # Ограничиваем до 10 источников
        ])
        prompt_parts.append(f"<sources>\n{sources_text}\n</sources>")
    
    # Task
    prompt_parts.append(f"<task>{task}</task>")
    
    # Format
    format_str = json.dumps(format_schema, indent=2, ensure_ascii=False) if format_schema else "{}"
    prompt_parts.append(f"<format>{format_str}</format>")
    
    prompt = "\n\n".join(prompt_parts)
    
    logger.debug("rctf_prompt_built", role=role, sources_count=len(sources) if sources else 0)
    
    return prompt


def build_rctf_from_schema(rctf: RCTFContext, sources: Optional[list[Source]] = None) -> str:
    """
    Строит R.C.T.F. промпт из RCTFContext объекта.
    
    Args:
        rctf: RCTFContext объект
        sources: Опциональные источники
        
    Returns:
        Форматированный промпт
    """
    return build_rctf_prompt(
        role=rctf.role,
        context_data=rctf.context_data,
        task=rctf.task,
        format_schema=rctf.format_schema,
        sources=sources,
    )


def extract_claims_from_response(
    llm_response: str,
    format_schema: Dict[str, Any],
) -> list[Dict[str, Any]]:
    """
    Извлекает утверждения (claims) из ответа LLM согласно format_schema.
    
    Args:
        llm_response: Ответ от LLM
        format_schema: Схема формата вывода
        
    Returns:
        Список утверждений
    """
    claims = []
    
    try:
        # Пытаемся извлечь JSON из ответа
        json_match = None
        
        # Ищем JSON блок
        json_patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{.*\}',
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, llm_response, re.DOTALL)
            if match:
                json_match = match.group(1) if pattern != r'\{.*\}' else match.group(0)
                break
        
        if json_match:
            data = json.loads(json_match)
            
            # Извлекаем claims согласно схеме
            if isinstance(data, dict):
                if "claims" in data:
                    claims = data["claims"]
                elif "results" in data:
                    claims = data["results"]
                else:
                    # Если структура нестандартная, пытаемся извлечь список
                    claims = [data] if isinstance(data, dict) else []
            elif isinstance(data, list):
                claims = data
        else:
            # Если JSON не найден, пытаемся парсить текст
            # Простая эвристика: каждое предложение - потенциальное утверждение
            lines = llm_response.split('\n')
            for line in lines:
                line = line.strip()
                if line and len(line) > 20:  # Минимальная длина утверждения
                    claims.append({"text": line, "extracted_from": "text_parsing"})
        
        logger.info("claims_extracted", count=len(claims))
        
    except Exception as e:
        logger.error("claims_extraction_failed", error=str(e))
        # Fallback: возвращаем весь ответ как одно утверждение
        claims = [{"text": llm_response, "extracted_from": "fallback"}]
    
    return claims


def create_default_claim_schema() -> Dict[str, Any]:
    """Создаёт схему по умолчанию для извлечения утверждений."""
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "category": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "source_url": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
        },
        "required": ["claims"],
    }

