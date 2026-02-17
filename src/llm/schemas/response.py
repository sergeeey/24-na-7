"""Базовые схемы для LLM ответов."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Базовая схема ответа от LLM."""
    text: str = Field(..., description="Текст ответа от LLM")
    tokens_used: Optional[int] = Field(None, description="Количество использованных токенов")
    latency_ms: Optional[float] = Field(None, description="Латентность запроса в миллисекундах")
    model: Optional[str] = Field(None, description="Модель LLM")
    reasoning_trace: Optional[Dict[str, Any]] = Field(None, description="Трассировка reasoning")
    
    class Config:
        extra = "allow"  # Разрешаем дополнительные поля


class LLMErrorResponse(BaseModel):
    """Схема ошибки от LLM."""
    error: str = Field(..., description="Текст ошибки")
    error_type: Optional[str] = Field(None, description="Тип ошибки")
    retryable: bool = Field(False, description="Можно ли повторить запрос")
    details: Optional[Dict[str, Any]] = Field(None, description="Дополнительные детали ошибки")
