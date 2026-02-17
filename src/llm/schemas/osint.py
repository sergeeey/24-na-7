"""Схемы для валидации OSINT ответов."""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, validator
from datetime import datetime


class Claim(BaseModel):
    """Утверждение из OSINT."""
    text: str = Field(..., description="Текст утверждения")
    source_urls: List[str] = Field(default_factory=list, description="URL источников")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Уверенность в утверждении")
    category: Optional[str] = Field(None, description="Категория утверждения")
    extracted_at: Optional[str] = Field(None, description="Время извлечения (ISO format)")
    extracted_from: Optional[str] = Field(None, description="Метод извлечения")
    
    @validator("source_urls", pre=True)
    def ensure_list(cls, v):
        """Обеспечиваем что source_urls - список."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v if isinstance(v, list) else []


class ValidatedClaim(BaseModel):
    """Валидированное утверждение через DeepConf."""
    claim: Claim = Field(..., description="Исходное утверждение")
    validated: bool = Field(False, description="Валидировано ли утверждение")
    validation_confidence: float = Field(0.5, ge=0.0, le=1.0, description="Уверенность в валидации")
    validation_reason: Optional[str] = Field(None, description="Причина валидации/отклонения")
    validated_at: Optional[str] = Field(None, description="Время валидации (ISO format)")


class OSINTResponse(BaseModel):
    """Ответ от OSINT миссии."""
    claims: List[Claim] = Field(default_factory=list, description="Список утверждений")
    validated_claims: List[ValidatedClaim] = Field(default_factory=list, description="Валидированные утверждения")
    sources_count: int = Field(0, ge=0, description="Количество источников")
    mission_id: Optional[str] = Field(None, description="ID миссии")
    status: Literal["pending", "completed", "failed"] = Field("pending", description="Статус миссии")
    
    @validator("claims", "validated_claims", pre=True)
    def ensure_list(cls, v):
        """Обеспечиваем что значение - список."""
        if v is None:
            return []
        return v if isinstance(v, list) else []
