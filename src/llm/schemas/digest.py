"""Схемы для валидации дайджестов и анализа записей."""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator


class EmotionItem(BaseModel):
    """Эмоция из анализа."""
    name: str = Field(..., description="Название эмоции")
    intensity: Optional[float] = Field(None, ge=0.0, le=1.0, description="Интенсивность эмоции (0-1)")


class TaskItem(BaseModel):
    """Задача из анализа."""
    task: str = Field(..., description="Описание задачи")
    priority: Literal["low", "medium", "high"] = Field("medium", description="Приоритет задачи")
    deadline: Optional[str] = Field(None, description="Дедлайн задачи (YYYY-MM-DD)")
    assignee: Optional[str] = Field(None, description="Исполнитель задачи")


class DigestOutput(BaseModel):
    """Выходные данные для анализа записи."""
    summary: Optional[str] = Field(None, description="Краткое саммари")
    emotions: List[str] = Field(default_factory=list, description="Список эмоций")
    actions: List[str] = Field(default_factory=list, description="Список действий")
    topics: List[str] = Field(default_factory=list, description="Список тем")
    urgency: Literal["low", "medium", "high"] = Field("medium", description="Срочность")
    key_points: Optional[List[str]] = Field(None, description="Ключевые моменты")
    sentiment: Optional[Literal["positive", "neutral", "negative"]] = Field(None, description="Тональность")
    tasks: Optional[List[TaskItem]] = Field(None, description="Извлечённые задачи")
    dominant_emotion: Optional[str] = Field(None, description="Доминирующая эмоция")
    intensity: Optional[float] = Field(None, ge=0.0, le=1.0, description="Общая интенсивность эмоций")
    
    @validator("emotions", "actions", "topics", pre=True)
    def ensure_list(cls, v):
        """Обеспечиваем что значение - список."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v if isinstance(v, list) else []


class DigestAnalysis(BaseModel):
    """Полный анализ записи через Few-Shot Actions."""
    action: str = Field(..., description="Тип действия (analyze_recording, summarize, extract_tasks, etc.)")
    output: DigestOutput = Field(..., description="Выходные данные анализа")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность в результате (0-1)")
    warning: Optional[str] = Field(None, description="Предупреждение о качестве результата")
    
    @validator("confidence", pre=True)
    def ensure_confidence(cls, v):
        """Обеспечиваем что confidence в диапазоне 0-1."""
        if v is None:
            return 0.5
        return max(0.0, min(1.0, float(v)))
