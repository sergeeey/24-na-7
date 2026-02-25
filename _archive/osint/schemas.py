"""
JSON схемы для OSINT KDS.

Определяет структуры данных для миссий, утверждений, валидации и вывода.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class Source(BaseModel):
    """Источник информации."""
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    scraped_at: Optional[str] = None
    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0)


class Claim(BaseModel):
    """Утверждение (claim) извлечённое из источников."""
    text: str
    source_urls: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    category: Optional[str] = None
    extracted_at: str


class ValidatedClaim(BaseModel):
    """Валидированное утверждение с метриками доверия."""
    claim: Claim
    validation_status: str = Field(..., pattern="^(supported|refuted|uncertain)$")
    critic_confidence: float = Field(ge=0.0, le=1.0)
    calibrated_confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    validated_at: str


class Task(BaseModel):
    """Задача в рамках OSINT миссии."""
    id: str
    query: str
    goggle_url: Optional[str] = None
    role: str
    instruction: str
    format_schema: Dict[str, Any] = Field(default_factory=dict)
    max_results: int = Field(default=10, ge=1, le=50)


class Mission(BaseModel):
    """OSINT миссия - стратегическая задача."""
    id: str
    name: str
    description: str
    tasks: List[Task]
    created_at: str
    target_confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class MissionResult(BaseModel):
    """Результат выполнения OSINT миссии."""
    mission_id: str
    completed_at: str
    tasks_completed: int
    total_claims: int
    validated_claims: int
    avg_confidence: float = Field(ge=0.0, le=1.0)
    claims: List[ValidatedClaim] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class RCTFContext(BaseModel):
    """R.C.T.F. контекст для промптов."""
    role: str
    context_data: Dict[str, Any]
    task: str
    format_schema: Dict[str, Any]













