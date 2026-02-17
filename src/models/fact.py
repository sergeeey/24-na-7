"""Pydantic модели для Fact Layer v4 — anti-hallucination система.

Модели:
    - SourceSpan: Точный диапазон текста в транскрипции
    - Fact: Атомарный, проверяемый факт из транскрипции
    - VerifiedFact: Факт после CoVe верификации
    - ValidationResult: Результат валидации факта
    - CoVeResult: Результат Chain-of-Verification проверки

Использование:
    from src.models.fact import Fact, SourceSpan

    fact = Fact(
        transcription_id="trans_001",
        fact_text="User's name is John Smith",
        confidence_score=0.95,
        extraction_method="cod",
        source_span=SourceSpan(
            start_char=12,
            end_char=32,
            text="my name is John Smith"
        )
    )
"""

from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator, model_validator


class SourceSpan(BaseModel):
    """Точный диапазон текста из транскрипции.

    Каждый факт должен иметь source_span, указывающий на исходный текст.
    Это обеспечивает grounding и предотвращает галлюцинации.

    Attributes:
        start_char: Позиция начала текста (≥0)
        end_char: Позиция конца текста (>start_char)
        text: Точный текст из источника

    Example:
        >>> span = SourceSpan(start_char=12, end_char=32, text="my name is John Smith")
        >>> span.start_char
        12
    """

    start_char: int = Field(
        ...,
        ge=0,
        description="Начальная позиция символа в транскрипции"
    )
    end_char: int = Field(
        ...,
        ge=0,
        description="Конечная позиция символа в транскрипции"
    )
    text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Точный текст из источника"
    )

    @field_validator("end_char")
    @classmethod
    def validate_span_range(cls, v, info):
        """Проверка что end_char > start_char."""
        if info.data.get("start_char") and v <= info.data["start_char"]:
            raise ValueError(
                f"end_char ({v}) должен быть больше start_char ({info.data['start_char']})"
            )
        return v

    @property
    def length(self) -> int:
        """Длина текста в символах."""
        return self.end_char - self.start_char

    def __repr__(self):
        """Читаемое представление."""
        preview = self.text[:30] + "..." if len(self.text) > 30 else self.text
        return f"SourceSpan({self.start_char}-{self.end_char}: '{preview}')"


class Fact(BaseModel):
    """Атомарный, проверяемый факт из транскрипции.

    Ключевые принципы:
    - Один факт = одно утверждение (атомарность)
    - Каждый факт имеет source_span (grounding)
    - Immutable после создания (no UPDATE)
    - Версионирование (fact_version)

    Attributes:
        fact_id: Уникальный идентификатор (генерируется автоматически)
        transcription_id: ID транскрипции-источника
        fact_text: Текст факта (10-500 символов)
        confidence_score: Уверенность в факте (0.0-1.0)
        extraction_method: Метод извлечения (cod|deepconf|cove)
        source_span: Диапазон текста в источнике
        fact_version: Версия формата (по умолчанию "1.0")
        timestamp: Время извлечения
        metadata: Дополнительные данные (опционально)

    Example:
        >>> fact = Fact(
        ...     transcription_id="trans_001",
        ...     fact_text="User's name is John Smith",
        ...     confidence_score=0.95,
        ...     extraction_method="cod",
        ...     source_span=SourceSpan(start_char=12, end_char=32, text="my name is John Smith")
        ... )
        >>> fact.fact_id
        'fact_a3f7b2c1d8e9'
    """

    fact_id: str = Field(
        default_factory=lambda: f"fact_{uuid4().hex[:12]}",
        description="Уникальный ID факта"
    )
    transcription_id: str = Field(
        ...,
        min_length=1,
        description="ID транскрипции-источника"
    )
    fact_text: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Текст факта (атомарное утверждение)"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Уверенность в факте (0-1)"
    )
    extraction_method: Literal["cod", "deepconf", "cove"] = Field(
        ...,
        description="Метод извлечения: cod (Chain-of-Density), deepconf (DeepConf), cove (CoVe)"
    )
    source_span: SourceSpan = Field(
        ...,
        description="Диапазон текста в источнике"
    )
    fact_version: str = Field(
        default="1.0",
        description="Версия формата факта"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Время извлечения факта"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Дополнительные метаданные"
    )

    @field_validator("fact_text")
    @classmethod
    def validate_atomicity(cls, v):
        """Проверка атомарности: один факт = одно утверждение.

        Факт не должен содержать:
        - " and " (compound claims)
        - ";" (multiple statements)
        - Вопросительные знаки (не утверждение)
        """
        v_lower = v.lower()

        # Проверка на compound claims
        if " and " in v_lower or ";" in v:
            raise ValueError(
                f"Факт должен быть атомарным (одно утверждение). "
                f"Найдено: '{v}'"
            )

        # Проверка на вопросы
        if "?" in v:
            raise ValueError(
                f"Факт должен быть утверждением, не вопросом. "
                f"Найдено: '{v}'"
            )

        # Проверка специфичности
        vague_patterns = [
            "something",
            "things",
            "stuff",
            "probably",
            "maybe",
            "might",
            "perhaps",
        ]

        for pattern in vague_patterns:
            if pattern in v_lower:
                raise ValueError(
                    f"Факт слишком расплывчат: '{v}'. "
                    f"Найден паттерн: '{pattern}'"
                )

        return v

    def to_db_dict(self) -> Dict[str, Any]:
        """Конвертация в формат для SQLite.

        Returns:
            Словарь с полями для INSERT в таблицу facts
        """
        import json

        return {
            "id": self.fact_id,
            "transcription_id": self.transcription_id,
            "fact_text": self.fact_text,
            "timestamp": self.timestamp,
            "confidence": self.confidence_score,
            "created_at": datetime.now(),
            # v4 новые поля
            "extracted_by": "v4-cove",
            "fact_version": self.fact_version,
            "confidence_score": self.confidence_score,
            "extraction_method": self.extraction_method,
            "source_span": json.dumps({
                "start_char": self.source_span.start_char,
                "end_char": self.source_span.end_char,
                "text": self.source_span.text,
            }),
        }

    def __repr__(self):
        """Читаемое представление."""
        text_preview = self.fact_text[:40] + "..." if len(self.fact_text) > 40 else self.fact_text
        return f"Fact({self.fact_id}: '{text_preview}', confidence={self.confidence_score:.2f})"


class ValidationResult(BaseModel):
    """Результат валидации факта.

    Используется в src/digest/validators.py для возврата результатов проверки.

    Attributes:
        is_valid: Факт прошёл валидацию?
        violations: Список нарушений
        severity: Максимальная серьёзность нарушений
        message: Текстовое описание результата

    Example:
        >>> result = ValidationResult(
        ...     is_valid=False,
        ...     violations=[{"rule": "atomicity", "severity": "HIGH", "detail": "Compound claim"}],
        ...     severity="HIGH",
        ...     message="Fact contains 'and' - not atomic"
        ... )
    """

    is_valid: bool = Field(
        ...,
        description="Факт прошёл валидацию?"
    )
    violations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Список нарушений"
    )
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        "LOW",
        description="Максимальная серьёзность нарушений"
    )
    message: str = Field(
        ...,
        description="Текстовое описание результата"
    )

    @staticmethod
    def aggregate(results: List["ValidationResult"]) -> "ValidationResult":
        """Агрегация результатов нескольких валидаторов.

        Args:
            results: Список ValidationResult от разных валидаторов

        Returns:
            Объединённый ValidationResult
        """
        is_valid = all(r.is_valid for r in results)
        violations = []
        for r in results:
            violations.extend(r.violations)

        severity_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        max_severity = max(
            (r.severity for r in results),
            key=lambda s: severity_order[s],
            default="LOW"
        )

        messages = [r.message for r in results if not r.is_valid]
        combined_message = "; ".join(messages) if messages else "All validations passed"

        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            severity=max_severity,
            message=combined_message,
        )


class CoVeResult(BaseModel):
    """Результат Chain-of-Verification проверки.

    CoVe Pipeline возвращает этот объект после 4 стадий:
    1. Planning (генерация вопросов)
    2. Execution (ответы из источника)
    3. Verification (проверка консистентности)
    4. Final (корректировка уверенности)

    Attributes:
        decision: Решение (PASS|NEEDS_REVISION|REJECT)
        original_confidence: Исходная уверенность
        adjusted_confidence: Скорректированная уверенность
        violations: Список нарушений с severity
        questions: Сгенерированные вопросы
        answers: Ответы из источника
        consistency_check: Результат проверки консистентности

    Example:
        >>> result = CoVeResult(
        ...     decision="PASS",
        ...     original_confidence=0.85,
        ...     adjusted_confidence=0.95,
        ...     violations=[],
        ...     questions=["Does user have headache?"],
        ...     answers=["Yes, user mentioned headache"],
        ...     consistency_check={"status": "consistent"}
        ... )
    """

    decision: Literal["PASS", "NEEDS_REVISION", "REJECT"] = Field(
        ...,
        description="Решение CoVe Pipeline"
    )
    original_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Исходная уверенность в факте"
    )
    adjusted_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Скорректированная уверенность после CoVe"
    )
    violations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Список нарушений с severity (LOW|MEDIUM|HIGH)"
    )
    questions: List[str] = Field(
        default_factory=list,
        description="Вопросы для верификации (Stage 1)"
    )
    answers: List[str] = Field(
        default_factory=list,
        description="Ответы из источника (Stage 2)"
    )
    consistency_check: Dict[str, Any] = Field(
        default_factory=dict,
        description="Результат проверки консистентности (Stage 3)"
    )

    @property
    def confidence_delta(self) -> float:
        """Изменение уверенности (adjusted - original)."""
        return self.adjusted_confidence - self.original_confidence

    @staticmethod
    def decide_from_violations(violations: List[Dict[str, Any]]) -> Literal["PASS", "NEEDS_REVISION", "REJECT"]:
        """Определение решения на основе нарушений.

        Логика:
        - ≥1 HIGH violation → REJECT
        - ≥3 MEDIUM violations → NEEDS_REVISION
        - Иначе → PASS

        Args:
            violations: Список нарушений с ключом "severity"

        Returns:
            Решение CoVe
        """
        high_count = sum(1 for v in violations if v.get("severity") == "HIGH")
        medium_count = sum(1 for v in violations if v.get("severity") == "MEDIUM")

        if high_count >= 1:
            return "REJECT"
        elif medium_count >= 3:
            return "NEEDS_REVISION"
        else:
            return "PASS"


class VerifiedFact(Fact):
    """Факт после CoVe верификации.

    Расширяет Fact дополнительными полями с результатами верификации.

    Attributes:
        (наследует все поля Fact)
        cove_result: Результат CoVe Pipeline
        verification_timestamp: Время верификации

    Example:
        >>> verified = VerifiedFact(
        ...     transcription_id="trans_001",
        ...     fact_text="User's name is John Smith",
        ...     confidence_score=0.95,
        ...     extraction_method="cove",
        ...     source_span=SourceSpan(...),
        ...     cove_result=CoVeResult(decision="PASS", ...)
        ... )
    """

    cove_result: CoVeResult = Field(
        ...,
        description="Результат Chain-of-Verification проверки"
    )
    verification_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Время верификации"
    )

    @model_validator(mode='after')
    def sync_confidence_with_cove(self):
        """Синхронизация confidence_score с CoVe результатом."""
        if self.cove_result:
            self.confidence_score = self.cove_result.adjusted_confidence
        return self


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_fact_from_extraction(
    transcription_id: str,
    fact_text: str,
    source_text: str,
    start_char: int,
    end_char: int,
    confidence: float,
    method: Literal["cod", "deepconf", "cove"] = "cod",
) -> Fact:
    """Удобная функция для создания Fact из результата извлечения.

    Args:
        transcription_id: ID транскрипции
        fact_text: Текст факта
        source_text: Текст из источника
        start_char: Начало диапазона
        end_char: Конец диапазона
        confidence: Уверенность (0-1)
        method: Метод извлечения

    Returns:
        Валидированный Fact объект

    Raises:
        ValidationError: Если данные не проходят валидацию

    Example:
        >>> fact = create_fact_from_extraction(
        ...     transcription_id="trans_001",
        ...     fact_text="User has headache",
        ...     source_text="I have a headache",
        ...     start_char=7,
        ...     end_char=23,
        ...     confidence=0.90
        ... )
    """
    source_span = SourceSpan(
        start_char=start_char,
        end_char=end_char,
        text=source_text,
    )

    return Fact(
        transcription_id=transcription_id,
        fact_text=fact_text,
        confidence_score=confidence,
        extraction_method=method,
        source_span=source_span,
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "SourceSpan",
    "Fact",
    "VerifiedFact",
    "ValidationResult",
    "CoVeResult",
    "create_fact_from_extraction",
]
