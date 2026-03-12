from unittest.mock import patch

from src.summarizer.few_shot import _extract_json_payload, generate_structured_output


def test_extract_json_payload_from_fenced_noise():
    payload = _extract_json_payload(
        'preface```json\n{"action":"summarize","output":{"summary":"ok"},"confidence":0.9}\n```tail'
    )
    assert payload == '{"action": "summarize", "output": {"summary": "ok"}, "confidence": 0.9}'


def test_generate_structured_output_parses_noisy_json_wrapper():
    mock_client = type(
        "MockClient",
        (),
        {
            "call": staticmethod(
                lambda *args, **kwargs: {
                    "text": 'Answer:\n```json\n{"action":"summarize","output":{"summary":"ok"},"confidence":0.9}\n```\nThanks',
                    "tokens_used": 10,
                    "latency_ms": 20,
                }
            )
        },
    )()

    with patch("src.summarizer.few_shot.get_llm_client", return_value=mock_client):
        result = generate_structured_output("Some text", action_type="summarize")

    assert result["action"] == "summarize"
    assert result["output"]["summary"] == "ok"
    assert result["confidence"] == 0.9
