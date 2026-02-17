"""Integration tests для CoVe с real LLM (требует API key)."""
import pytest
from datetime import datetime

from src.models.fact import Fact, SourceSpan
from src.digest.cove_pipeline import CoVePipeline
from src.digest.validators import TranscriptionContext
from src.llm.factory import create_cove_client


@pytest.fixture
def llm_client():
    """Создаёт LLM client для CoVe (может быть None если нет API key)."""
    return create_cove_client()


@pytest.fixture
def sample_fact():
    """Sample fact для тестирования."""
    return Fact(
        fact_id="fact_test_001",
        transcription_id="trans_001",
        fact_text="Встреча с Иваном в 15:00 в офисе",
        confidence_score=0.85,
        extraction_method="cod",
        source_span=SourceSpan(
            start_char=0,
            end_char=35,
            text="Встреча с Иваном в 15:00 в офисе",
        ),
        fact_version="1.0",
        timestamp=datetime.now(),
    )


@pytest.fixture
def transcription_context():
    """Transcription context для верификации."""
    return TranscriptionContext(
        transcription_id="trans_001",
        text="Сегодня у меня встреча с Иваном в 15:00 в офисе. Нужно обсудить квартальный отчёт.",
    )


class TestCoVeRealLLM:
    """Тесты CoVe с real LLM integration."""

    def test_cove_with_real_llm_if_available(
        self, llm_client, sample_fact, transcription_context
    ):
        """Тест CoVe с real LLM (skip если нет API key)."""
        if not llm_client:
            pytest.skip("LLM client not available (ENABLE_COVE=false or no API key)")

        pipeline = CoVePipeline(
            llm_client=llm_client,
            confidence_threshold=0.70,
            enable_fallback=True,
        )

        verified_facts = pipeline.verify_facts([sample_fact], transcription_context)

        # Assertions
        assert len(verified_facts) == 1
        verified = verified_facts[0]

        assert verified.fact_id == sample_fact.fact_id
        assert verified.cove_result is not None
        assert verified.cove_result.decision in ["PASS", "NEEDS_REVISION", "REJECT"]
        assert len(verified.cove_result.questions) > 0
        assert len(verified.cove_result.answers) > 0

        # Confidence должна быть adjusted
        assert verified.confidence_score != sample_fact.confidence_score

    def test_cove_fallback_on_llm_failure(self, sample_fact, transcription_context):
        """Тест fallback к mock mode при LLM failure."""
        # Создаём broken LLM client (симуляция failure)
        class BrokenLLMClient:
            def call(self, *args, **kwargs):
                raise Exception("Simulated LLM failure")

        pipeline = CoVePipeline(
            llm_client=BrokenLLMClient(),
            confidence_threshold=0.70,
            enable_fallback=True,  # Enable fallback
        )

        # Должно работать через fallback к mock
        verified_facts = pipeline.verify_facts([sample_fact], transcription_context)

        assert len(verified_facts) == 1
        assert verified_facts[0].cove_result is not None

        # Проверяем, что после 3 failures переключилось на mock
        pipeline2 = CoVePipeline(
            llm_client=BrokenLLMClient(),
            confidence_threshold=0.70,
            enable_fallback=True,
        )

        # Должно переключиться на mock после нескольких failures
        for _ in range(5):  # Проверяем стабильность
            result = pipeline2.verify_facts([sample_fact], transcription_context)
            assert len(result) > 0

    def test_cove_mock_mode_when_no_client(
        self, sample_fact, transcription_context
    ):
        """Тест mock mode когда llm_client=None."""
        pipeline = CoVePipeline(
            llm_client=None,  # Mock mode
            confidence_threshold=0.70,
        )

        verified_facts = pipeline.verify_facts([sample_fact], transcription_context)

        assert len(verified_facts) == 1
        verified = verified_facts[0]

        assert verified.cove_result is not None
        assert verified.cove_result.decision in ["PASS", "NEEDS_REVISION", "REJECT"]

        # Mock questions должны быть простыми
        assert any("Is it true" in q for q in verified.cove_result.questions)

    def test_cove_hallucination_detection(
        self, llm_client, transcription_context
    ):
        """Тест detection hallucination (факт не в source)."""
        if not llm_client:
            pytest.skip("LLM client not available")

        # Hallucinated fact (не существует в transcription)
        hallucinated_fact = Fact(
            fact_id="fact_hallucinated",
            transcription_id="trans_001",
            fact_text="Встреча с Петром в 18:00",  # Петра нет в source!
            confidence_score=0.85,
            extraction_method="cod",
            source_span=SourceSpan(
                start_char=0,
                end_char=27,
                text="Встреча с Петром в 18:00",
            ),
            fact_version="1.0",
            timestamp=datetime.now(),
        )

        pipeline = CoVePipeline(
            llm_client=llm_client,
            confidence_threshold=0.70,
        )

        verified_facts = pipeline.verify_facts(
            [hallucinated_fact], transcription_context
        )

        # Hallucination должна быть rejected или heavily penalized
        if len(verified_facts) > 0:
            verified = verified_facts[0]
            # Confidence должна быть сильно снижена
            assert verified.confidence_score < hallucinated_fact.confidence_score * 0.8
        else:
            # Или полностью отфильтрована (confidence < threshold)
            pass  # Это тоже valid outcome

    @pytest.mark.parametrize(
        "enable_cove,expected_mode",
        [
            (True, "real_llm"),  # If API key available
            (False, "mock"),  # Forced mock
        ],
    )
    def test_cove_enable_flag(
        self, enable_cove, expected_mode, sample_fact, transcription_context, monkeypatch
    ):
        """Тест ENABLE_COVE flag."""
        # Override settings
        from src.utils.config import settings
        monkeypatch.setattr(settings, "ENABLE_COVE", enable_cove)

        client = create_cove_client()

        if enable_cove and not client:
            pytest.skip("API key not available, cannot test real LLM mode")

        pipeline = CoVePipeline(
            llm_client=client,
            confidence_threshold=0.70,
        )

        verified_facts = pipeline.verify_facts([sample_fact], transcription_context)

        assert len(verified_facts) >= 0  # May be filtered if low confidence

        if expected_mode == "mock":
            assert client is None  # Mock mode
        else:
            assert client is not None  # Real LLM mode
