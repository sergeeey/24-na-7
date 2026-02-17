"""
Guardrails — валидация и защита выходных данных LLM.

Features:
- Output schema validation
- Toxic content detection
- PII masking
- Fact consistency checks
"""
import re
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from src.utils.logging import get_logger

logger = get_logger("guardrails")


class ValidationError(Enum):
    """Типы ошибок валидации."""
    SCHEMA_VIOLATION = "schema_violation"
    TOXIC_CONTENT = "toxic_content"
    PII_LEAK = "pii_leak"
    HALLUCINATION = "hallucination"
    INCONSISTENCY = "inconsistency"
    TOO_LONG = "too_long"
    EMPTY = "empty"


@dataclass
class GuardrailResult:
    """Результат проверки guardrail."""
    is_valid: bool
    errors: List[Dict[str, Any]] = field(default_factory=list)
    sanitized_output: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_error(self, error_type: ValidationError, message: str, details: Optional[Dict] = None):
        """Добавляет ошибку в результат."""
        self.errors.append({
            "type": error_type.value,
            "message": message,
            "details": details or {},
        })


# Pydantic модели для валидации output

class SummaryOutput(BaseModel):
    """Схема для summary output."""
    summary: str = Field(..., min_length=10, max_length=5000)
    key_facts: List[str] = Field(default_factory=list, max_length=20)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    
    @field_validator("summary")
    def summary_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Summary cannot be empty")
        return v


class FactOutput(BaseModel):
    """Схема для извлечения фактов."""
    facts: List[Dict[str, Any]] = Field(..., max_length=50)
    
    @field_validator("facts")
    def validate_facts(cls, v):
        for fact in v:
            if "text" not in fact:
                raise ValueError("Each fact must have 'text' field")
            if len(fact["text"]) < 5:
                raise ValueError("Fact text too short")
        return v


class IntentOutput(BaseModel):
    """Схема для определения интента."""
    intent: str = Field(..., pattern=r"^(create_note|search|summarize|unknown)$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    entities: List[Dict[str, str]] = Field(default_factory=list)


class PIIDetector:
    """Детектор PII (Personally Identifiable Information)."""
    
    # Паттерны для различных типов PII
    PATTERNS = {
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"),
        "api_key": re.compile(r"\b(?:sk-|pk-)[a-zA-Z0-9]{20,}\b"),
    }
    
    MASK = "[REDACTED]"
    
    def detect(self, text: str) -> List[Dict[str, Any]]:
        """Обнаруживает PII в тексте."""
        findings = []
        
        for pii_type, pattern in self.PATTERNS.items():
            matches = pattern.finditer(text)
            for match in matches:
                findings.append({
                    "type": pii_type,
                    "start": match.start(),
                    "end": match.end(),
                    "value": match.group(),
                })
        
        return findings
    
    def mask(self, text: str) -> str:
        """Маскирует PII в тексте."""
        masked = text
        
        for pii_type, pattern in self.PATTERNS.items():
            masked = pattern.sub(f"[{pii_type.upper()}: {self.MASK}]", masked)
        
        return masked
    
    def has_pii(self, text: str) -> bool:
        """Проверяет наличие PII."""
        return len(self.detect(text)) > 0


class ToxicityDetector:
    """Простой детектор токсичного контента (rule-based)."""
    
    # Список токсичных паттернов (упрощенный)
    TOXIC_PATTERNS = [
        r"\b(kill|murder|die|death)\s+(?:yourself|himself|herself|them)\b",
        r"\b(hate|destroy|attack)\s+(?:all|every)\b",
        r"\b(bomb|terror|shoot|stab)\b",
        r"\b(?:make|create)\s+(?:a\s+)?(?:bomb|weapon|virus)\b",
    ]
    
    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.TOXIC_PATTERNS]
    
    def is_toxic(self, text: str) -> Tuple[bool, List[str]]:
        """Проверяет текст на токсичность."""
        matches = []
        
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                matches.append(pattern.pattern[:50])
        
        return len(matches) > 0, matches


class OutputValidator:
    """Валидатор выходных данных LLM."""
    
    def __init__(
        self,
        max_length: int = 10000,
        block_pii: bool = True,
        block_toxic: bool = True,
        require_json_schema: bool = False,
    ):
        self.max_length = max_length
        self.block_pii = block_pii
        self.block_toxic = block_toxic
        self.require_json_schema = require_json_schema
        
        self.pii_detector = PIIDetector()
        self.toxicity_detector = ToxicityDetector()
    
    def validate_length(self, text: str, result: GuardrailResult) -> bool:
        """Проверяет длину текста."""
        if len(text) > self.max_length:
            result.add_error(
                ValidationError.TOO_LONG,
                f"Output too long: {len(text)} > {self.max_length}",
                {"length": len(text), "max": self.max_length},
            )
            return False
        return True
    
    def validate_not_empty(self, text: str, result: GuardrailResult) -> bool:
        """Проверяет что текст не пустой."""
        if not text or not text.strip():
            result.add_error(ValidationError.EMPTY, "Output is empty")
            return False
        return True
    
    def validate_pii(self, text: str, result: GuardrailResult) -> Tuple[bool, str]:
        """Проверяет наличие PII."""
        pii_findings = self.pii_detector.detect(text)
        
        if pii_findings:
            # Маскируем PII
            masked = self.pii_detector.mask(text)
            
            if self.block_pii:
                result.add_error(
                    ValidationError.PII_LEAK,
                    f"PII detected: {len(pii_findings)} occurrences",
                    {"findings": pii_findings},
                )
                return False, masked
            
            # Логируем, но пропускаем (с маскировкой)
            logger.warning("pii_detected_but_allowed", count=len(pii_findings))
            return True, masked
        
        return True, text
    
    def validate_toxicity(self, text: str, result: GuardrailResult) -> bool:
        """Проверяет токсичность."""
        is_toxic, patterns = self.toxicity_detector.is_toxic(text)
        
        if is_toxic:
            if self.block_toxic:
                result.add_error(
                    ValidationError.TOXIC_CONTENT,
                    "Toxic content detected",
                    {"patterns_matched": patterns},
                )
                return False
            
            logger.warning("toxic_content_detected_but_allowed", patterns=patterns)
        
        return True
    
    def validate_json_schema(
        self,
        text: str,
        schema_model: type[BaseModel],
        result: GuardrailResult,
    ) -> Tuple[bool, Optional[BaseModel]]:
        """Валидирует JSON по Pydantic схеме."""
        try:
            # Пытаемся распарсить JSON
            data = json.loads(text)
            
            # Валидируем по схеме
            validated = schema_model(**data)
            return True, validated
            
        except json.JSONDecodeError as e:
            result.add_error(
                ValidationError.SCHEMA_VIOLATION,
                f"Invalid JSON: {str(e)}",
            )
            return False, None
            
        except Exception as e:
            result.add_error(
                ValidationError.SCHEMA_VIOLATION,
                f"Schema validation failed: {str(e)}",
            )
            return False, None


class Guardrails:
    """
    Главный класс для применения guardrails к output LLM.
    
    Usage:
        guardrails = Guardrails()
        result = guardrails.validate(llm_output, schema=SummaryOutput)
        
        if result.is_valid:
            return result.sanitized_output
        else:
            handle_errors(result.errors)
    """
    
    def __init__(self):
        self.validator = OutputValidator()
    
    def validate(
        self,
        output: str,
        schema: Optional[type[BaseModel]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardrailResult:
        """
        Полная валидация output.
        
        Args:
            output: Текст от LLM
            schema: Опциональная Pydantic схема для валидации
            context: Контекст для дополнительных проверок
            
        Returns:
            GuardrailResult с результатами
        """
        result = GuardrailResult(is_valid=True)
        current_output = output
        
        # 1. Проверка на пустоту
        if not self.validator.validate_not_empty(output, result):
            result.is_valid = False
            return result
        
        # 2. Проверка длины
        if not self.validator.validate_length(output, result):
            result.is_valid = False
            current_output = output[:self.validator.max_length]
        
        # 3. Проверка PII
        pii_ok, current_output = self.validator.validate_pii(current_output, result)
        if not pii_ok:
            result.is_valid = False
        
        # 4. Проверка токсичности
        if not self.validator.validate_toxicity(current_output, result):
            result.is_valid = False
        
        # 5. Валидация по схеме (если указана)
        if schema:
            schema_ok, validated = self.validator.validate_json_schema(
                current_output, schema, result
            )
            if schema_ok:
                result.metadata["validated_data"] = validated
            else:
                result.is_valid = False
        
        result.sanitized_output = current_output if result.is_valid else None
        
        # Логирование
        if not result.is_valid:
            logger.warning(
                "guardrails_validation_failed",
                errors_count=len(result.errors),
                error_types=[e["type"] for e in result.errors],
            )
        
        return result
    
    def validate_summary(self, output: str) -> GuardrailResult:
        """Удобный метод для валидации summary."""
        return self.validate(output, schema=SummaryOutput)
    
    def validate_facts(self, output: str) -> GuardrailResult:
        """Удобный метод для валидации facts."""
        return self.validate(output, schema=FactOutput)
    
    def validate_intent(self, output: str) -> GuardrailResult:
        """Удобный метод для валидации intent."""
        return self.validate(output, schema=IntentOutput)


# Синглтон
_default_guardrails: Optional[Guardrails] = None


def get_guardrails() -> Guardrails:
    """Возвращает синглтон Guardrails."""
    global _default_guardrails
    if _default_guardrails is None:
        _default_guardrails = Guardrails()
    return _default_guardrails


def validate_output(
    output: str,
    schema: Optional[type[BaseModel]] = None,
) -> GuardrailResult:
    """Удобная функция для быстрой валидации."""
    return get_guardrails().validate(output, schema=schema)
