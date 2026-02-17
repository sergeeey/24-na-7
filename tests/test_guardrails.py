"""
Тесты для Guardrails (P0-4) — валидация выходных данных LLM.
"""
import pytest
import json

from src.utils.guardrails import (
    Guardrails,
    PIIDetector,
    ToxicityDetector,
    OutputValidator,
    GuardrailResult,
    ValidationError,
    SummaryOutput,
    IntentOutput,
    validate_output,
    get_guardrails,
)


class TestPIIDetector:
    """Тесты детектора PII."""
    
    @pytest.fixture
    def detector(self):
        return PIIDetector()
    
    def test_detects_ssn(self, detector):
        """Обнаружение SSN."""
        text = "My SSN is 123-45-6789"
        findings = detector.detect(text)
        assert len(findings) == 1
        assert findings[0]["type"] == "ssn"
    
    def test_detects_email(self, detector):
        """Обнаружение email."""
        text = "Contact me at test@example.com"
        findings = detector.detect(text)
        assert len(findings) == 1
        assert findings[0]["type"] == "email"
    
    def test_detects_credit_card(self, detector):
        """Обнаружение кредитной карты."""
        text = "Card: 4111-1111-1111-1111"
        findings = detector.detect(text)
        assert len(findings) == 1
        assert findings[0]["type"] == "credit_card"
    
    def test_detects_api_key(self, detector):
        """Обнаружение API ключа."""
        text = "Key: sk-abcdefghijklmnopqrstuvwxyz123456"
        findings = detector.detect(text)
        assert len(findings) >= 1
        assert any(f["type"] == "api_key" for f in findings)
    
    def test_masks_pii(self, detector):
        """Маскировка PII."""
        text = "Email: test@example.com, Phone: 123-456-7890"
        masked = detector.mask(text)
        assert "test@example.com" not in masked
        assert "123-456-7890" not in masked
        assert "[EMAIL:" in masked or "[REDACTED]" in masked
    
    def test_has_pii_returns_bool(self, detector):
        """has_pii возвращает bool."""
        assert detector.has_pii("Email: test@example.com") is True
        assert detector.has_pii("Just regular text") is False


class TestToxicityDetector:
    """Тесты детектора токсичности."""
    
    @pytest.fixture
    def detector(self):
        return ToxicityDetector()
    
    def test_detects_self_harm(self, detector):
        """Обнаружение self-harm контента."""
        is_toxic, patterns = detector.is_toxic("You should kill yourself")
        assert is_toxic is True
    
    def test_detects_violence(self, detector):
        """Обнаружение призывов к насилию."""
        is_toxic, patterns = detector.is_toxic("Attack all users")
        assert is_toxic is True
    
    def test_safe_text_passes(self, detector):
        """Безопасный текст не детектируется."""
        is_toxic, patterns = detector.is_toxic("Please summarize this document")
        assert is_toxic is False
        assert patterns == []


class TestOutputValidator:
    """Тесты валидатора output."""
    
    @pytest.fixture
    def validator(self):
        return OutputValidator()
    
    def test_validates_length(self, validator):
        """Валидация длины текста."""
        result = GuardrailResult(is_valid=True)
        long_text = "A" * 15000
        is_valid = validator.validate_length(long_text, result)
        assert is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0]["type"] == ValidationError.TOO_LONG.value
    
    def test_validates_not_empty(self, validator):
        """Валидация непустоты."""
        result = GuardrailResult(is_valid=True)
        is_valid = validator.validate_not_empty("", result)
        assert is_valid is False
        assert result.errors[0]["type"] == ValidationError.EMPTY.value
    
    def test_validates_pii_blocks(self, validator):
        """Валидация PII блокирует если block_pii=True."""
        result = GuardrailResult(is_valid=True)
        text = "Email: test@example.com"
        is_valid, masked = validator.validate_pii(text, result)
        assert is_valid is False
        assert result.errors[0]["type"] == ValidationError.PII_LEAK.value
    
    def test_validates_pii_allows_when_disabled(self):
        """Валидация PII пропускает если block_pii=False."""
        validator = OutputValidator(block_pii=False)
        result = GuardrailResult(is_valid=True)
        text = "Email: test@example.com"
        is_valid, masked = validator.validate_pii(text, result)
        assert is_valid is True  # Не блокирует, но маскирует
    
    def test_validates_toxicity(self, validator):
        """Валидация токсичности."""
        result = GuardrailResult(is_valid=True)
        is_valid = validator.validate_toxicity("Attack all users", result)
        assert is_valid is False
        assert result.errors[0]["type"] == ValidationError.TOXIC_CONTENT.value
    
    def test_validates_json_schema_success(self, validator):
        """Успешная валидация JSON схемы."""
        result = GuardrailResult(is_valid=True)
        json_text = json.dumps({
            "summary": "This is a test summary",
            "key_facts": ["Fact 1", "Fact 2"],
            "confidence_score": 0.9
        })
        is_valid, validated = validator.validate_json_schema(
            json_text, SummaryOutput, result
        )
        assert is_valid is True
        assert validated is not None
        assert validated.summary == "This is a test summary"
    
    def test_validates_json_schema_failure(self, validator):
        """Неудачная валидация JSON схемы."""
        result = GuardrailResult(is_valid=True)
        json_text = json.dumps({
            "summary": "",  # Пустой summary — ошибка
            "confidence_score": 1.5  # > 1 — ошибка
        })
        is_valid, validated = validator.validate_json_schema(
            json_text, SummaryOutput, result
        )
        assert is_valid is False
        assert validated is None
        assert result.errors[0]["type"] == ValidationError.SCHEMA_VIOLATION.value


class TestPydanticModels:
    """Тесты Pydantic моделей."""
    
    def test_summary_output_valid(self):
        """Валидный SummaryOutput."""
        data = SummaryOutput(
            summary="This is a valid summary",
            key_facts=["Fact 1", "Fact 2"],
            confidence_score=0.85
        )
        assert data.summary == "This is a valid summary"
        assert len(data.key_facts) == 2
    
    def test_summary_output_invalid_empty(self):
        """Невалидный SummaryOutput (пустой)."""
        with pytest.raises(Exception):
            SummaryOutput(summary="", confidence_score=0.5)
    
    def test_summary_output_invalid_confidence(self):
        """Невалидный confidence_score."""
        with pytest.raises(Exception):
            SummaryOutput(
                summary="Valid text",
                confidence_score=1.5  # > 1
            )
    
    def test_intent_output_valid(self):
        """Валидный IntentOutput."""
        data = IntentOutput(intent="create_note", confidence=0.9)
        assert data.intent == "create_note"
    
    def test_intent_output_invalid_enum(self):
        """Невалидный intent (не из enum)."""
        with pytest.raises(Exception):
            IntentOutput(intent="invalid_intent", confidence=0.9)


class TestGuardrails:
    """Тесты главного класса Guardrails."""
    
    @pytest.fixture
    def guardrails(self):
        return Guardrails()
    
    def test_validates_safe_output(self, guardrails):
        """Валидация безопасного output."""
        result = guardrails.validate("This is a safe summary text")
        assert result.is_valid is True
        assert result.sanitized_output == "This is a safe summary text"
    
    def test_blocks_pii_output(self, guardrails):
        """Блокировка output с PII."""
        result = guardrails.validate("Contact: test@example.com")
        assert result.is_valid is False
        assert any(e["type"] == ValidationError.PII_LEAK.value for e in result.errors)
    
    def test_blocks_toxic_output(self, guardrails):
        """Блокировка токсичного output."""
        result = guardrails.validate("You should attack all users")
        assert result.is_valid is False
        assert any(e["type"] == ValidationError.TOXIC_CONTENT.value for e in result.errors)
    
    def test_validates_with_schema(self, guardrails):
        """Валидация со схемой."""
        json_text = json.dumps({
            "summary": "Valid summary",
            "key_facts": ["Fact 1"],
            "confidence_score": 0.8
        })
        result = guardrails.validate(json_text, schema=SummaryOutput)
        assert result.is_valid is True
        assert "validated_data" in result.metadata
    
    def test_validate_summary_convenience_method(self, guardrails):
        """Удобный метод validate_summary."""
        json_text = json.dumps({
            "summary": "Meeting summary",
            "key_facts": ["Fact 1"],
            "confidence_score": 0.9
        })
        result = guardrails.validate_summary(json_text)
        assert result.is_valid is True
    
    def test_validate_facts_convenience_method(self, guardrails):
        """Удобный метод validate_facts."""
        json_text = json.dumps({
            "facts": [
                {"text": "Fact 1 content"},
                {"text": "Fact 2 content"}
            ]
        })
        result = guardrails.validate_facts(json_text)
        assert result.is_valid is True


class TestGetGuardrails:
    """Тесты синглтона."""
    
    def test_returns_singleton(self):
        """Возвращает один и тот же объект."""
        g1 = get_guardrails()
        g2 = get_guardrails()
        assert g1 is g2
    
    def test_validate_output_convenience_function(self):
        """Удобная функция validate_output."""
        result = validate_output("Safe text")
        assert result.is_valid is True


class TestGuardrailResult:
    """Тесты GuardrailResult."""
    
    def test_add_error(self):
        """Добавление ошибки."""
        result = GuardrailResult(is_valid=True)
        result.add_error(ValidationError.TOXIC_CONTENT, "Test message", {"detail": "x"})
        assert len(result.errors) == 1
        assert result.errors[0]["type"] == ValidationError.TOXIC_CONTENT.value
    
    def test_default_values(self):
        """Значения по умолчанию."""
        result = GuardrailResult(is_valid=True)
        assert result.errors == []
        assert result.metadata == {}
        assert result.sanitized_output is None
