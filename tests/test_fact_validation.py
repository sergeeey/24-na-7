"""Тесты для Fact Layer v4 validators.

Проверяет:
    - Pydantic модели (Fact, SourceSpan, ValidationResult)
    - Валидаторы (Atomicity, Grounding, Consistency, Specificity)
    - Агрегатор (FactValidator)
    - Сценарии из test fixtures
"""

import pytest
from datetime import datetime

from src.models.fact import (
    Fact,
    SourceSpan,
    ValidationResult,
    CoVeResult,
    create_fact_from_extraction,
)
from src.digest.validators import (
    TranscriptionContext,
    AtomicityValidator,
    GroundingValidator,
    ConsistencyValidator,
    SpecificityValidator,
    FactValidator,
)
from tests.fixtures.fact_samples import (
    SAMPLE_TRANSCRIPTIONS,
    SAMPLE_FACTS,
    get_sample_transcription,
    get_sample_fact,
)


# ============================================================================
# PYDANTIC MODELS TESTS
# ============================================================================

class TestSourceSpan:
    """Тесты для SourceSpan model."""

    def test_valid_source_span(self):
        """Валидный source_span создаётся успешно."""
        span = SourceSpan(
            start_char=12,
            end_char=32,
            text="my name is John Smith"
        )

        assert span.start_char == 12
        assert span.end_char == 32
        assert span.length == 20
        assert "John Smith" in span.text

    def test_invalid_span_range(self):
        """end_char <= start_char должен вызвать ошибку."""
        with pytest.raises(ValueError, match="должен быть больше"):
            SourceSpan(
                start_char=32,
                end_char=12,  # ОШИБКА: меньше start_char
                text="invalid"
            )

    def test_equal_span_range(self):
        """end_char == start_char должен вызвать ошибку."""
        with pytest.raises(ValueError, match="должен быть больше"):
            SourceSpan(
                start_char=10,
                end_char=10,  # ОШИБКА: равен start_char
                text=""
            )


class TestFact:
    """Тесты для Fact model."""

    def test_valid_fact_creation(self):
        """Валидный факт создаётся успешно."""
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

        assert fact.transcription_id == "trans_001"
        assert fact.confidence_score == 0.95
        assert fact.fact_version == "1.0"
        assert fact.extraction_method == "cod"
        assert fact.fact_id.startswith("fact_")

    def test_atomicity_validation_compound_claim(self):
        """Факт с 'and' должен быть отклонён."""
        with pytest.raises(ValueError, match="атомарным"):
            Fact(
                transcription_id="trans_002",
                fact_text="User has headache and nausea",  # Compound claim
                confidence_score=0.80,
                extraction_method="cod",
                source_span=SourceSpan(start_char=0, end_char=20, text="headache and nausea")
            )

    def test_atomicity_validation_semicolon(self):
        """Факт с ';' должен быть отклонён."""
        with pytest.raises(ValueError, match="атомарным"):
            Fact(
                transcription_id="trans_003",
                fact_text="Symptom A; Symptom B",
                confidence_score=0.70,
                extraction_method="cod",
                source_span=SourceSpan(start_char=0, end_char=20, text="symptoms")
            )

    def test_atomicity_validation_question(self):
        """Вопрос должен быть отклонён."""
        with pytest.raises(ValueError, match="утверждением, не вопросом"):
            Fact(
                transcription_id="trans_004",
                fact_text="Does user have headache?",
                confidence_score=0.60,
                extraction_method="cod",
                source_span=SourceSpan(start_char=0, end_char=10, text="headache")
            )

    def test_specificity_validation_something(self):
        """Факт с 'something' должен быть отклонён."""
        with pytest.raises(ValueError, match="расплывчат"):
            Fact(
                transcription_id="trans_005",
                fact_text="User mentioned something about health",
                confidence_score=0.50,
                extraction_method="cod",
                source_span=SourceSpan(start_char=0, end_char=10, text="health")
            )

    def test_specificity_validation_maybe(self):
        """Факт с 'maybe' должен быть отклонён."""
        with pytest.raises(ValueError, match="расплывчат"):
            Fact(
                transcription_id="trans_006",
                fact_text="User maybe has fever",
                confidence_score=0.40,
                extraction_method="cod",
                source_span=SourceSpan(start_char=0, end_char=10, text="fever")
            )

    def test_fact_to_db_dict(self):
        """Конвертация в DB dict работает."""
        fact = Fact(
            transcription_id="trans_007",
            fact_text="User took ibuprofen",
            confidence_score=0.88,
            extraction_method="deepconf",
            source_span=SourceSpan(start_char=50, end_char=70, text="took ibuprofen")
        )

        db_dict = fact.to_db_dict()

        assert db_dict["id"] == fact.fact_id
        assert db_dict["transcription_id"] == "trans_007"
        assert db_dict["fact_text"] == "User took ibuprofen"
        assert db_dict["extracted_by"] == "v4-cove"
        assert db_dict["fact_version"] == "1.0"
        assert db_dict["extraction_method"] == "deepconf"
        assert "start_char" in db_dict["source_span"]


class TestValidationResult:
    """Тесты для ValidationResult model."""

    def test_aggregate_all_valid(self):
        """Агрегация всех валидных результатов."""
        results = [
            ValidationResult(is_valid=True, violations=[], severity="LOW", message="OK 1"),
            ValidationResult(is_valid=True, violations=[], severity="LOW", message="OK 2"),
        ]

        aggregated = ValidationResult.aggregate(results)

        assert aggregated.is_valid is True
        assert aggregated.severity == "LOW"
        assert len(aggregated.violations) == 0

    def test_aggregate_with_violations(self):
        """Агрегация с нарушениями."""
        results = [
            ValidationResult(
                is_valid=False,
                violations=[{"rule": "atomicity", "severity": "HIGH"}],
                severity="HIGH",
                message="Atomicity failed"
            ),
            ValidationResult(
                is_valid=False,
                violations=[{"rule": "specificity", "severity": "MEDIUM"}],
                severity="MEDIUM",
                message="Specificity failed"
            ),
        ]

        aggregated = ValidationResult.aggregate(results)

        assert aggregated.is_valid is False
        assert aggregated.severity == "HIGH"  # Максимальная severity
        assert len(aggregated.violations) == 2

    def test_aggregate_mixed(self):
        """Агрегация смешанных результатов."""
        results = [
            ValidationResult(is_valid=True, violations=[], severity="LOW", message="OK"),
            ValidationResult(
                is_valid=False,
                violations=[{"rule": "grounding", "severity": "MEDIUM"}],
                severity="MEDIUM",
                message="Grounding failed"
            ),
        ]

        aggregated = ValidationResult.aggregate(results)

        assert aggregated.is_valid is False
        assert aggregated.severity == "MEDIUM"
        assert len(aggregated.violations) == 1


class TestCoVeResult:
    """Тесты для CoVeResult model."""

    def test_cove_result_creation(self):
        """CoVe result создаётся успешно."""
        result = CoVeResult(
            decision="PASS",
            original_confidence=0.85,
            adjusted_confidence=0.95,
            violations=[],
            questions=["Does user have headache?"],
            answers=["Yes"],
            consistency_check={"status": "consistent"}
        )

        assert result.decision == "PASS"
        assert abs(result.confidence_delta - 0.10) < 0.01  # Floating point tolerance

    def test_decide_from_violations_pass(self):
        """Нет нарушений → PASS."""
        violations = []
        decision = CoVeResult.decide_from_violations(violations)

        assert decision == "PASS"

    def test_decide_from_violations_reject(self):
        """≥1 HIGH violation → REJECT."""
        violations = [
            {"severity": "HIGH", "detail": "Hallucination detected"},
        ]
        decision = CoVeResult.decide_from_violations(violations)

        assert decision == "REJECT"

    def test_decide_from_violations_needs_revision(self):
        """≥3 MEDIUM violations → NEEDS_REVISION."""
        violations = [
            {"severity": "MEDIUM", "detail": "Issue 1"},
            {"severity": "MEDIUM", "detail": "Issue 2"},
            {"severity": "MEDIUM", "detail": "Issue 3"},
        ]
        decision = CoVeResult.decide_from_violations(violations)

        assert decision == "NEEDS_REVISION"

    def test_decide_from_violations_pass_with_low(self):
        """Только LOW violations → PASS."""
        violations = [
            {"severity": "LOW", "detail": "Minor issue"},
            {"severity": "LOW", "detail": "Minor issue 2"},
        ]
        decision = CoVeResult.decide_from_violations(violations)

        assert decision == "PASS"


# ============================================================================
# VALIDATORS TESTS
# ============================================================================

class TestAtomicityValidator:
    """Тесты для AtomicityValidator."""

    def test_valid_atomic_fact(self):
        """Атомарный факт проходит валидацию."""
        validator = AtomicityValidator()
        fact = Fact(
            transcription_id="trans_001",
            fact_text="User has headache",
            confidence_score=0.90,
            extraction_method="cod",
            source_span=SourceSpan(start_char=0, end_char=10, text="headache")
        )

        result = validator.validate(fact)

        assert result.is_valid is True
        assert len(result.violations) == 0

    def test_compound_claim_detected(self):
        """Compound claim обнаруживается (только через validator, не Pydantic)."""
        validator = AtomicityValidator()

        # Создаём факт напрямую через __init__ (минуя Pydantic валидацию)
        from pydantic import ValidationError
        try:
            fact = Fact.model_construct(  # Обход Pydantic валидации
                transcription_id="trans_002",
                fact_text="User has headache and nausea",
                confidence_score=0.80,
                extraction_method="cod",
                source_span=SourceSpan(start_char=0, end_char=20, text="text"),
                fact_id="fact_test_001",
                timestamp=datetime.now(),
                fact_version="1.0"
            )

            result = validator.validate(fact)

            assert result.is_valid is False
            assert len(result.violations) >= 1
            assert result.violations[0]["rule"] == "atomicity"
            assert result.violations[0]["severity"] == "HIGH"

        except ValidationError:
            # Если Pydantic всё равно поймал — тест тоже проходит
            pytest.skip("Pydantic validation prevents creating compound claim")


class TestGroundingValidator:
    """Тесты для GroundingValidator."""

    def test_valid_grounding(self):
        """Факт с правильным source_span проходит валидацию."""
        validator = GroundingValidator(fuzzy_threshold=0.70)

        transcription = SAMPLE_TRANSCRIPTIONS["simple_medical"]
        context = TranscriptionContext(
            transcription_id=transcription["id"],
            text=transcription["text"]
        )

        fact = Fact(
            transcription_id=transcription["id"],
            fact_text="User's name is John Smith",
            confidence_score=0.95,
            extraction_method="cod",
            source_span=SourceSpan(
                start_char=7,
                end_char=26,
                text="name is John Smith."
            )
        )

        result = validator.validate(fact, context)

        assert result.is_valid is True
        assert len(result.violations) == 0

    def test_out_of_bounds_span(self):
        """source_span вне границ транскрипции."""
        validator = GroundingValidator()

        context = TranscriptionContext(
            transcription_id="trans_001",
            text="Short text"  # Длина: 10
        )

        fact = Fact(
            transcription_id="trans_001",
            fact_text="Invalid fact",
            confidence_score=0.50,
            extraction_method="cod",
            source_span=SourceSpan(
                start_char=0,
                end_char=100,  # Вне границ!
                text="text"
            )
        )

        result = validator.validate(fact, context)

        assert result.is_valid is False
        assert result.severity == "CRITICAL"
        assert "out of bounds" in result.message

    def test_text_mismatch(self):
        """source_span.text не совпадает с реальным текстом."""
        validator = GroundingValidator()

        context = TranscriptionContext(
            transcription_id="trans_002",
            text="Hello, my name is Jane Doe"
        )

        fact = Fact(
            transcription_id="trans_002",
            fact_text="User's name is Jane Doe",
            confidence_score=0.80,
            extraction_method="cod",
            source_span=SourceSpan(
                start_char=7,
                end_char=26,
                text="my name is John Smith"  # НЕПРАВИЛЬНО! Реально: "my name is Jane Doe"
            )
        )

        result = validator.validate(fact, context)

        assert result.is_valid is False
        assert any(v["rule"] == "grounding" for v in result.violations)


class TestConsistencyValidator:
    """Тесты для ConsistencyValidator."""

    def test_consistent_fact(self):
        """Факт и источник консистентны."""
        validator = ConsistencyValidator()

        context = TranscriptionContext(
            transcription_id="trans_001",
            text="I have a headache"
        )

        fact = Fact(
            transcription_id="trans_001",
            fact_text="User has headache",
            confidence_score=0.90,
            extraction_method="cod",
            source_span=SourceSpan(start_char=7, end_char=17, text="a headache")
        )

        result = validator.validate(fact, context)

        assert result.is_valid is True

    def test_negation_mismatch(self):
        """Факт утверждает, источник отрицает."""
        validator = ConsistencyValidator()

        context = TranscriptionContext(
            transcription_id="trans_002",
            text="I don't have fever"
        )

        fact = Fact(
            transcription_id="trans_002",
            fact_text="User has fever",  # Противоречие!
            confidence_score=0.60,
            extraction_method="cod",
            source_span=SourceSpan(start_char=2, end_char=18, text="don't have fever")  # Включаем negation
        )

        result = validator.validate(fact, context)

        assert result.is_valid is False
        assert result.violations[0]["severity"] == "HIGH"
        assert "Negation mismatch" in result.violations[0]["detail"]


class TestSpecificityValidator:
    """Тесты для SpecificityValidator."""

    def test_specific_fact(self):
        """Конкретный факт проходит валидацию."""
        validator = SpecificityValidator()

        fact = Fact(
            transcription_id="trans_001",
            fact_text="Headache started Monday morning",
            confidence_score=0.92,
            extraction_method="cod",
            source_span=SourceSpan(start_char=0, end_char=20, text="Monday morning")
        )

        result = validator.validate(fact)

        assert result.is_valid is True

    def test_vague_something(self):
        """Факт с 'something' отклоняется (только validator, не Pydantic)."""
        validator = SpecificityValidator()

        # Обход Pydantic
        fact = Fact.model_construct(
            transcription_id="trans_002",
            fact_text="User mentioned something",
            confidence_score=0.50,
            extraction_method="cod",
            source_span=SourceSpan(start_char=0, end_char=10, text="text"),
            fact_id="fact_test_002",
            timestamp=datetime.now(),
            fact_version="1.0"
        )

        result = validator.validate(fact)

        assert result.is_valid is False
        assert result.violations[0]["severity"] == "MEDIUM"


class TestFactValidator:
    """Тесты для агрегатора FactValidator."""

    def test_all_validations_pass(self):
        """Все валидаторы проходят."""
        validator = FactValidator(fuzzy_threshold=0.70)

        transcription = SAMPLE_TRANSCRIPTIONS["simple_medical"]
        context = TranscriptionContext(
            transcription_id=transcription["id"],
            text=transcription["text"]
        )

        fact = Fact(
            transcription_id=transcription["id"],
            fact_text="User's name is John Smith",
            confidence_score=0.95,
            extraction_method="cod",
            source_span=SourceSpan(
                start_char=7,
                end_char=26,
                text="name is John Smith."
            )
        )

        result = validator.validate_fact_sync(fact, context)

        assert result.is_valid is True
        assert result.severity == "LOW"

    def test_multiple_validators_fail(self):
        """Несколько валидаторов fail."""
        validator = FactValidator()

        context = TranscriptionContext(
            transcription_id="trans_001",
            text="I don't have fever"
        )

        # Факт с negation mismatch + out of bounds
        fact = Fact.model_construct(
            transcription_id="trans_001",
            fact_text="User has fever",  # Negation mismatch
            confidence_score=0.50,
            extraction_method="cod",
            source_span=SourceSpan(
                start_char=0,
                end_char=200,  # Out of bounds
                text="fever"
            ),
            fact_id="fact_test_003",
            timestamp=datetime.now(),
            fact_version="1.0"
        )

        result = validator.validate_fact_sync(fact, context)

        assert result.is_valid is False
        assert len(result.violations) >= 1  # At least grounding CRITICAL
        assert result.severity in ["HIGH", "CRITICAL"]


# ============================================================================
# INTEGRATION TESTS (с test fixtures)
# ============================================================================

class TestIntegrationWithFixtures:
    """Интеграционные тесты с использованием fixtures."""

    def test_atomic_valid_fact(self):
        """Atomic valid fact из fixtures проходит все валидации."""
        validator = FactValidator(fuzzy_threshold=0.70)

        fact_data = get_sample_fact("atomic_valid")
        transcription_data = get_sample_transcription("simple_medical")

        fact = Fact(**fact_data)
        context = TranscriptionContext(
            transcription_id=transcription_data["id"],
            text=transcription_data["text"]
        )

        result = validator.validate_fact_sync(fact, context)

        assert result.is_valid is True


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================

class TestUtilityFunctions:
    """Тесты для utility functions."""

    def test_create_fact_from_extraction(self):
        """create_fact_from_extraction работает."""
        fact = create_fact_from_extraction(
            transcription_id="trans_001",
            fact_text="Headache started Monday",
            source_text="started Monday morning",
            start_char=85,
            end_char=107,
            confidence=0.92
        )

        assert fact.transcription_id == "trans_001"
        assert fact.confidence_score == 0.92
        assert fact.source_span.start_char == 85
        assert fact.source_span.length == 22
