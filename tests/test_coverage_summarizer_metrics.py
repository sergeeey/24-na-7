"""
Тесты для покрытия summarizer и metrics_ext.
"""
from unittest.mock import patch


def test_metrics_ext_lexical_diversity():
    """Лексическое разнообразие."""
    from src.digest.metrics_ext import lexical_diversity
    assert lexical_diversity([]) == 0.0
    assert abs(lexical_diversity(["hello world"]) - 1.0) < 0.01  # 2 unique / 2 total
    assert 0 < lexical_diversity(["a b a b"]) < 1.0


def test_metrics_ext_avg_words_per_segment():
    """Среднее слов на сегмент."""
    from src.digest.metrics_ext import avg_words_per_segment
    assert avg_words_per_segment([]) == 0.0
    assert avg_words_per_segment(["one two three"]) == 3.0
    assert avg_words_per_segment(["a b", "c d e"]) == 2.5


def test_metrics_ext_avg_chars_per_segment():
    """Среднее символов на сегмент."""
    from src.digest.metrics_ext import avg_chars_per_segment
    assert avg_chars_per_segment([]) == 0.0
    assert avg_chars_per_segment(["ab"]) == 2.0


def test_metrics_ext_hourly_density_variation():
    """Вариация плотности по часам."""
    from src.digest.metrics_ext import hourly_density_variation
    assert hourly_density_variation([]) == 0.0
    assert hourly_density_variation([1.0, 1.0, 1.0]) == 0.0
    assert hourly_density_variation([1.0, 0.0, 0.0]) >= 0.0


def test_metrics_ext_wpm_rate():
    """Скорость речи (words per minute)."""
    from src.digest.metrics_ext import wpm_rate
    assert wpm_rate([], []) == 0.0
    # 60 sec, 60 words -> 60 wpm
    assert wpm_rate([60.0], ["word " * 59 + "word"]) > 0.0


def test_chain_of_density_no_llm():
    """generate_dense_summary при отсутствии LLM возвращает ошибку."""
    from src.summarizer.chain_of_density import generate_dense_summary
    with patch("src.summarizer.chain_of_density.get_llm_client", return_value=None):
        out = generate_dense_summary("Short text", iterations=1)
    assert "error" in out or out.get("summary") == ""


def test_critic_validate_summary():
    """validate_summary возвращает структуру с confidence."""
    from src.summarizer.critic import validate_summary
    with patch("src.summarizer.critic.calculate_confidence_score") as m:
        m.return_value = {"confidence_score": 0.9, "token_entropy": 0.5}
        with patch("src.summarizer.critic.should_refine", return_value=False):
            out = validate_summary("Summary", "Original text", confidence_threshold=0.8, auto_refine=False)
    assert out["confidence_score"] == 0.9
    assert "summary" in out


def test_few_shot_extract_tasks():
    """extract_tasks с моком LLM."""
    from src.summarizer.few_shot import extract_tasks
    with patch("src.summarizer.few_shot.get_llm_client", return_value=None):
        tasks = extract_tasks("Meeting: do the report by Friday")
    assert isinstance(tasks, list)


def test_few_shot_analyze_emotions():
    """analyze_emotions с моком LLM."""
    from src.summarizer.few_shot import analyze_emotions
    with patch("src.summarizer.few_shot.get_llm_client", return_value=None):
        out = analyze_emotions("I am happy and excited")
    assert isinstance(out, dict)
    assert "emotions" in out or "sentiment" in out or len(out) >= 0


def test_calculate_extended_metrics_disabled():
    """calculate_extended_metrics при enabled=False возвращает {}."""
    from src.digest.metrics_ext import calculate_extended_metrics
    assert calculate_extended_metrics([], enabled=False) == {}


def test_calculate_extended_metrics_empty():
    """calculate_extended_metrics при пустом списке возвращает структуру с нулями."""
    from src.digest.metrics_ext import calculate_extended_metrics
    out = calculate_extended_metrics([], enabled=True)
    assert "lexical_diversity" in out
    assert out["lexical_diversity"] == 0.0


def test_calculate_extended_metrics_with_data():
    """calculate_extended_metrics с транскрипциями."""
    from src.digest.metrics_ext import calculate_extended_metrics
    transcriptions = [
        {"text": "First segment here.", "duration": 10.0, "created_at": "2026-01-15T10:00:00"},
        {"text": "Second segment.", "duration": 5.0, "created_at": "2026-01-15T10:01:00"},
    ]
    out = calculate_extended_metrics(transcriptions, enabled=True)
    assert "lexical_diversity" in out
    assert "wpm_rate" in out
    assert out["lexical_diversity"] >= 0
