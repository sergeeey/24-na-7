"""Validators для Fact Layer v4 — multi-layer validation.

Валидаторы:
    - AtomicityValidator: Проверка атомарности (один факт = одно утверждение)
    - GroundingValidator: Проверка grounding (факт должен быть в источнике)
    - ConsistencyValidator: Проверка консистентности (нет противоречий)
    - SpecificityValidator: Проверка специфичности (не расплывчато)
    - FactValidator: Агрегатор всех валидаторов

Использование:
    from src.digest.validators import FactValidator
    from src.models.fact import Fact, ValidationResult

    validator = FactValidator()
    result = await validator.validate_fact(fact, context)

    if result.is_valid:
        # Сохранить факт
    else:
        # Обработать нарушения
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

from src.models.fact import Fact, ValidationResult


@dataclass
class TranscriptionContext:
    """Контекст транскрипции для валидации.

    Attributes:
        transcription_id: ID транскрипции
        text: Полный текст транскрипции
        segments: Сегменты транскрипции (опционально)
        metadata: Дополнительные метаданные
    """
    transcription_id: str
    text: str
    segments: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class AtomicityValidator:
    """Проверка атомарности: один факт = одно утверждение.

    Факт не должен содержать:
    - Множественные утверждения через "and"
    - Списки через ";" или ","
    - Вопросительные знаки (не утверждение)
    """

    def __init__(self):
        """Инициализация валидатора."""
        self.compound_patterns = [
            r"\band\b",  # "headache and nausea"
            r";",        # "symptom A; symptom B"
        ]

        self.non_statement_patterns = [
            r"\?",       # Вопросы
        ]

    def validate(self, fact: Fact) -> ValidationResult:
        """Проверка атомарности факта.

        Args:
            fact: Факт для проверки

        Returns:
            ValidationResult с результатом проверки
        """
        violations = []
        text_lower = fact.fact_text.lower()

        # Проверка на compound claims
        for pattern in self.compound_patterns:
            if re.search(pattern, text_lower):
                violations.append({
                    "rule": "atomicity",
                    "severity": "HIGH",
                    "pattern": pattern,
                    "detail": f"Факт содержит множественные утверждения (паттерн: {pattern})",
                })

        # Проверка на не-утверждения
        for pattern in self.non_statement_patterns:
            if re.search(pattern, fact.fact_text):
                violations.append({
                    "rule": "atomicity",
                    "severity": "HIGH",
                    "pattern": pattern,
                    "detail": "Факт должен быть утверждением, не вопросом",
                })

        is_valid = len(violations) == 0
        severity = "HIGH" if violations else "LOW"
        message = "Atomicity check passed" if is_valid else f"Found {len(violations)} atomicity violations"

        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            severity=severity,
            message=message,
        )


class GroundingValidator:
    """Проверка grounding: факт должен быть в источнике.

    Использует fuzzy matching для поиска факта в транскрипции.
    Threshold по умолчанию: 80% (настраивается).
    """

    def __init__(self, fuzzy_threshold: float = 0.80):
        """Инициализация валидатора.

        Args:
            fuzzy_threshold: Порог для fuzzy matching (0.0-1.0)
        """
        self.fuzzy_threshold = fuzzy_threshold

        if not RAPIDFUZZ_AVAILABLE:
            import warnings
            warnings.warn(
                "rapidfuzz not available, using simple substring matching. "
                "Install rapidfuzz for better grounding validation: pip install rapidfuzz"
            )

    def validate(self, fact: Fact, context: TranscriptionContext) -> ValidationResult:
        """Проверка grounding факта в источнике.

        Args:
            fact: Факт для проверки
            context: Контекст транскрипции

        Returns:
            ValidationResult с результатом проверки
        """
        violations = []

        # Проверка 1: source_span должен быть в пределах транскрипции
        if fact.source_span.end_char > len(context.text):
            violations.append({
                "rule": "grounding",
                "severity": "CRITICAL",
                "detail": f"source_span.end_char ({fact.source_span.end_char}) > len(transcription) ({len(context.text)})",
            })

            return ValidationResult(
                is_valid=False,
                violations=violations,
                severity="CRITICAL",
                message="source_span out of bounds",
            )

        # Проверка 2: source_span.text совпадает с текстом в транскрипции
        actual_text = context.text[fact.source_span.start_char:fact.source_span.end_char]

        if actual_text != fact.source_span.text:
            violations.append({
                "rule": "grounding",
                "severity": "HIGH",
                "detail": f"source_span.text не совпадает с транскрипцией. "
                         f"Expected: '{fact.source_span.text}', Got: '{actual_text}'",
            })

        # Проверка 3: Fuzzy matching факта в источнике
        grounding_score = self._calculate_grounding_score(
            fact.fact_text,
            fact.source_span.text,
            context.text
        )

        if grounding_score < self.fuzzy_threshold:
            violations.append({
                "rule": "grounding",
                "severity": "MEDIUM",
                "detail": f"Grounding score ({grounding_score:.2f}) < threshold ({self.fuzzy_threshold})",
                "grounding_score": grounding_score,
            })

        is_valid = len(violations) == 0
        severity = max((v["severity"] for v in violations), default="LOW")
        message = "Grounding check passed" if is_valid else f"Found {len(violations)} grounding violations"

        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            severity=severity,
            message=message,
        )

    def _calculate_grounding_score(
        self,
        fact_text: str,
        source_span_text: str,
        full_transcription: str
    ) -> float:
        """Вычисление grounding score через fuzzy matching.

        Args:
            fact_text: Текст факта
            source_span_text: Текст из source_span
            full_transcription: Полная транскрипция

        Returns:
            Grounding score (0.0-1.0)
        """
        if RAPIDFUZZ_AVAILABLE:
            # Метод 1: Fuzzy matching факта к source_span
            score1 = fuzz.partial_ratio(
                fact_text.lower(),
                source_span_text.lower()
            ) / 100.0

            # Метод 2: Fuzzy matching source_span к транскрипции
            score2 = fuzz.partial_ratio(
                source_span_text.lower(),
                full_transcription.lower()
            ) / 100.0

            # Итоговый score — среднее
            return (score1 + score2) / 2.0
        else:
            # Fallback: простая проверка подстроки
            fact_lower = fact_text.lower()
            source_lower = source_span_text.lower()
            trans_lower = full_transcription.lower()

            if source_lower in trans_lower and any(word in source_lower for word in fact_lower.split()):
                return 0.85  # Достаточно высокий score
            elif source_lower in trans_lower:
                return 0.70  # Средний score
            else:
                return 0.30  # Низкий score


class ConsistencyValidator:
    """Проверка консистентности: нет противоречий.

    Обнаруживает:
    - Negation mismatches (факт утверждает, источник отрицает)
    - Contradictory claims
    """

    def __init__(self):
        """Инициализация валидатора."""
        self.negation_patterns = [
            r"\bno\b", r"\bnot\b", r"\bnever\b", r"\bdon't\b", r"\bdoesn't\b",
            r"\bhadn't\b", r"\bhasn't\b", r"\bhaven't\b", r"\bwon't\b",
            r"\bнет\b", r"\bне\b", r"\bникогда\b",  # Russian
        ]

    def validate(self, fact: Fact, context: TranscriptionContext) -> ValidationResult:
        """Проверка консистентности факта.

        Args:
            fact: Факт для проверки
            context: Контекст транскрипции

        Returns:
            ValidationResult с результатом проверки
        """
        violations = []

        # Проверка negation mismatch
        fact_has_negation = self._has_negation(fact.fact_text)
        source_has_negation = self._has_negation(fact.source_span.text)

        # XOR: только один должен иметь negation
        if fact_has_negation != source_has_negation:
            violations.append({
                "rule": "consistency",
                "severity": "HIGH",
                "detail": "Negation mismatch: факт и источник имеют разную полярность",
                "fact_negation": fact_has_negation,
                "source_negation": source_has_negation,
            })

        is_valid = len(violations) == 0
        severity = "HIGH" if violations else "LOW"
        message = "Consistency check passed" if is_valid else f"Found {len(violations)} consistency violations"

        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            severity=severity,
            message=message,
        )

    def _has_negation(self, text: str) -> bool:
        """Проверка наличия отрицания в тексте.

        Args:
            text: Текст для проверки

        Returns:
            True если есть отрицание
        """
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in self.negation_patterns)


class SpecificityValidator:
    """Проверка специфичности: факт не должен быть расплывчатым.

    Запрещённые паттерны:
    - "something", "things" (неопределённость)
    - "probably", "maybe" (неуверенность)
    - "mentioned" без конкретики
    """

    def __init__(self):
        """Инициализация валидатора."""
        self.vague_patterns = [
            r"\bsomething\b", r"\bthings\b", r"\bstuff\b",
            r"\bprobably\b", r"\bmaybe\b", r"\bmight\b", r"\bperhaps\b",
            r"\bmentioned\b",  # "User mentioned something" без деталей
            r"\bчто-то\b", r"\bвозможно\b", r"\bнаверное\b",  # Russian
        ]

    def validate(self, fact: Fact) -> ValidationResult:
        """Проверка специфичности факта.

        Args:
            fact: Факт для проверки

        Returns:
            ValidationResult с результатом проверки
        """
        violations = []
        text_lower = fact.fact_text.lower()

        for pattern in self.vague_patterns:
            if re.search(pattern, text_lower):
                violations.append({
                    "rule": "specificity",
                    "severity": "MEDIUM",
                    "pattern": pattern,
                    "detail": f"Факт содержит расплывчатый паттерн: {pattern}",
                })

        is_valid = len(violations) == 0
        severity = "MEDIUM" if violations else "LOW"
        message = "Specificity check passed" if is_valid else f"Found {len(violations)} specificity violations"

        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            severity=severity,
            message=message,
        )


class FactValidator:
    """Агрегатор всех валидаторов.

    Запускает все валидаторы параллельно (asyncio.gather в будущем)
    и агрегирует результаты.
    """

    def __init__(
        self,
        fuzzy_threshold: float = 0.80,
        enable_grounding: bool = True,
        enable_consistency: bool = True,
        enable_specificity: bool = True,
    ):
        """Инициализация агрегатора.

        Args:
            fuzzy_threshold: Порог для grounding validator
            enable_grounding: Включить grounding validator
            enable_consistency: Включить consistency validator
            enable_specificity: Включить specificity validator
        """
        self.atomicity_validator = AtomicityValidator()
        self.grounding_validator = GroundingValidator(fuzzy_threshold) if enable_grounding else None
        self.consistency_validator = ConsistencyValidator() if enable_consistency else None
        self.specificity_validator = SpecificityValidator() if enable_specificity else None

    async def validate_fact(
        self,
        fact: Fact,
        context: Optional[TranscriptionContext] = None
    ) -> ValidationResult:
        """Валидация факта всеми валидаторами.

        Args:
            fact: Факт для проверки
            context: Контекст транскрипции (требуется для grounding/consistency)

        Returns:
            Агрегированный ValidationResult
        """
        results = []

        # 1. Atomicity (не требует контекста)
        results.append(self.atomicity_validator.validate(fact))

        # 2. Specificity (не требует контекста)
        if self.specificity_validator:
            results.append(self.specificity_validator.validate(fact))

        # 3. Grounding (требует контекста)
        if self.grounding_validator and context:
            results.append(self.grounding_validator.validate(fact, context))

        # 4. Consistency (требует контекста)
        if self.consistency_validator and context:
            results.append(self.consistency_validator.validate(fact, context))

        # Агрегация результатов
        return ValidationResult.aggregate(results)

    def validate_fact_sync(
        self,
        fact: Fact,
        context: Optional[TranscriptionContext] = None
    ) -> ValidationResult:
        """Синхронная версия validate_fact (для тестов).

        Args:
            fact: Факт для проверки
            context: Контекст транскрипции

        Returns:
            Агрегированный ValidationResult
        """
        results = []

        results.append(self.atomicity_validator.validate(fact))

        if self.specificity_validator:
            results.append(self.specificity_validator.validate(fact))

        if self.grounding_validator and context:
            results.append(self.grounding_validator.validate(fact, context))

        if self.consistency_validator and context:
            results.append(self.consistency_validator.validate(fact, context))

        return ValidationResult.aggregate(results)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "TranscriptionContext",
    "AtomicityValidator",
    "GroundingValidator",
    "ConsistencyValidator",
    "SpecificityValidator",
    "FactValidator",
]
