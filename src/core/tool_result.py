"""
ToolResult — единый контракт ответа для всех тулов Query Engine.

ПОЧЕМУ единый контракт:
  Без него каждый тул возвращает произвольный dict → orchestrator не может
  сравнить confidence, объединить evidence, посчитать общую уверенность.
  С контрактом: любой тул совместим с любым orchestrator-ом.

Использование:
  from src.core.tool_result import ToolResult, ConfidenceLabel, tool_error

  return ToolResult(
      data={"events": events},
      evidence_ids=[e["id"] for e in events],
      confidence=0.85,
      tool_name="query_events",
      db_query_ms=42.0,
  )
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ConfidenceLabel(str, Enum):
    HIGH = "high"          # ≥0.8 — прямой ответ
    MEDIUM = "medium"      # 0.6–0.79 — аккуратный ответ
    LOW = "low"            # 0.4–0.59 — "есть признаки, но не полностью"
    SPECULATIVE = "speculative"  # <0.4 — требует предупреждения + уточнения


def _label_from_score(score: float) -> ConfidenceLabel:
    if score >= 0.8:
        return ConfidenceLabel.HIGH
    if score >= 0.6:
        return ConfidenceLabel.MEDIUM
    if score >= 0.4:
        return ConfidenceLabel.LOW
    return ConfidenceLabel.SPECULATIVE


class ToolResult(BaseModel):
    """Единица ответа от любого тула Query Engine."""

    # Полезная нагрузка
    data: Any = None

    # Доказательная база
    evidence_ids: list[str] = Field(default_factory=list)

    # Уверенность
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: ConfidenceLabel = ConfidenceLabel.SPECULATIVE

    # Мета
    tool_name: str
    db_query_ms: float = 0.0
    error: str | None = None
    warning: str | None = None

    @model_validator(mode="after")
    def _derive_label(self) -> "ToolResult":
        # Автоматически выводим label из score
        self.confidence_label = _label_from_score(self.confidence)

        # Проверка: high confidence требует ≥2 evidence
        if self.confidence_label == ConfidenceLabel.HIGH and len(self.evidence_ids) < 2:
            self.confidence = 0.79
            self.confidence_label = ConfidenceLabel.MEDIUM
            self.warning = (
                self.warning or ""
            ) + " [auto-downgrade: high confidence requires ≥2 evidence]"

        return self

    @classmethod
    def empty(cls, tool_name: str, reason: str = "no_data") -> "ToolResult":
        """Пустой результат — нет данных."""
        return cls(
            data=None,
            evidence_ids=[],
            confidence=0.0,
            tool_name=tool_name,
            warning=f"No data found: {reason}",
        )

    @classmethod
    def error_result(cls, tool_name: str, error: str) -> "ToolResult":
        """Ошибочный результат — тул упал."""
        return cls(
            data=None,
            evidence_ids=[],
            confidence=0.0,
            tool_name=tool_name,
            error=error,
        )

    def is_reliable(self) -> bool:
        """Результат достаточно надёжен для прямого ответа."""
        return self.confidence >= 0.6 and self.error is None

    def is_speculative(self) -> bool:
        return self.confidence_label == ConfidenceLabel.SPECULATIVE

    def to_api_dict(self, include_evidence: bool = False) -> dict[str, Any]:
        """Сериализация для API-ответа. Evidence скрыто по умолчанию."""
        out: dict[str, Any] = {
            "data": self.data,
            "confidence": round(self.confidence, 2),
            "confidence_label": self.confidence_label.value,
            "tool": self.tool_name,
            "db_query_ms": round(self.db_query_ms, 1),
        }
        if self.error:
            out["error"] = self.error
        if self.warning:
            out["warning"] = self.warning
        if include_evidence:
            out["evidence_ids"] = self.evidence_ids
        return out


def add_meta(data: dict, *, confidence: float, evidence_count: int = 0, tool: str = "") -> dict:
    """
    Добавляет _meta к существующему dict ответа без изменения его структуры.

    Используется для обратно-совместимой миграции старых роутеров:
      return add_meta(existing_response, confidence=0.85, evidence_count=10)

    Клиент который не знает о _meta — игнорирует его.
    Новый клиент (orchestrator, /ask) — читает _meta для merge_confidence.
    """
    label = _label_from_score(confidence)
    data["_meta"] = {
        "confidence": round(confidence, 2),
        "confidence_label": label.value,
        "evidence_count": evidence_count,
        "tool": tool,
    }
    return data


class ToolTimer:
    """Контекстный менеджер для замера времени DB-запроса."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "ToolTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
