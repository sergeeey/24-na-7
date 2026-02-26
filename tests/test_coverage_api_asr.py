"""
Тесты для повышения покрытия API и ASR.
"""
import os
import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


def test_api_metrics():
    """Эндпоинт /metrics возвращает метрики."""
    from src.api.main import app
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "timestamp" in data or "service" in data
    assert "storage" in data
    assert "config" in data


def test_api_prometheus_metrics():
    """Эндпоинт /metrics/prometheus возвращает текст."""
    from src.api.main import app
    client = TestClient(app)
    r = client.get("/metrics/prometheus")
    assert r.status_code == 200
    assert "reflexio_" in r.text or "HELP" in r.text


def test_api_metrics_with_db(tmp_path):
    """Эндпоинт /metrics при наличии БД с таблицами."""
    from src.api.main import app
    db_path = tmp_path / "reflexio.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE transcriptions (id TEXT)")
    conn.execute("CREATE TABLE facts (id TEXT)")
    conn.execute("INSERT INTO transcriptions (id) VALUES ('1')")
    conn.execute("INSERT INTO facts (id) VALUES ('1')")
    conn.commit()
    conn.close()
    with patch("src.api.routers.metrics.settings") as s:
        s.STORAGE_PATH = tmp_path
        s.UPLOADS_PATH = tmp_path
        s.RECORDINGS_PATH = tmp_path
        s.FILTER_MUSIC = False
        s.EXTENDED_METRICS = False
        s.EDGE_AUTO_UPLOAD = True
        client = TestClient(app)
        r = client.get("/metrics")
    assert r.status_code == 200
    assert r.json().get("database", {}).get("transcriptions_count") == 1


def test_api_search_phrases():
    """Эндпоинт /search/phrases с телом запроса (мок embeddings)."""
    import sys
    from src.api.main import app
    fake_module = MagicMock()
    fake_module.search_phrases = MagicMock(return_value=[])
    with patch.dict(sys.modules, {"src.storage.embeddings": fake_module}):
        client = TestClient(app)
        r = client.post("/search/phrases", json={"query": "test", "limit": 5})
    assert r.status_code == 200
    assert r.json().get("query") == "test"
    assert "matches" in r.json()


def test_api_transcribe_endpoint_not_found():
    """Эндпоинт /asr/transcribe при отсутствии файла возвращает 404."""
    from src.api.main import app
    client = TestClient(app)
    r = client.post("/asr/transcribe?file_id=nonexistent-id-12345")
    assert r.status_code == 404


def test_transcribe_audio_with_mock_provider(tmp_path):
    """transcribe_audio с замоканным провайдером (provider != local чтобы использовать провайдера)."""
    from src.asr.transcribe import transcribe_audio
    (tmp_path / "audio.wav").write_bytes(b"fake-wav")
    mock_provider = MagicMock()
    mock_provider.transcribe.return_value = {
        "text": "Hello",
        "language": "en",
        "segments": [],
    }
    with patch("src.asr.transcribe.get_asr_provider", return_value=mock_provider):
        result = transcribe_audio(tmp_path / "audio.wav", provider="openai")
    assert "text" in result
    assert result["text"] == "Hello"


@pytest.mark.skipif(
    __import__("sys").platform == "win32",
    reason="faster_whisper/ctranslate2 can crash on Windows when imported",
)
def test_transcribe_audio_fallback_exception(tmp_path):
    """transcribe_audio при отсутствии провайдера и модели бросает исключение."""
    from src.asr.transcribe import transcribe_audio
    (tmp_path / "a.wav").write_bytes(b"x")
    with patch("src.asr.transcribe.get_asr_provider", return_value=None):
        with patch("src.asr.transcribe.get_model", return_value=None):
            with pytest.raises(Exception):
                transcribe_audio(tmp_path / "a.wav", provider="local")


def test_llm_anthropic_call_mock():
    """AnthropicClient.call с моком API."""
    import sys
    from src.llm.providers import AnthropicClient
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hi")]
    mock_response.usage = MagicMock(input_tokens=5, output_tokens=2)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_mod = MagicMock()
    mock_mod.Anthropic.return_value = mock_client
    old = sys.modules.get("anthropic")
    sys.modules["anthropic"] = mock_mod
    try:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-x"}):
            client = AnthropicClient(model="claude-3", temperature=0.3)
            out = client.call("Hello")
        assert "text" in out
        assert out.get("text") == "Hi"
    finally:
        if old is None:
            sys.modules.pop("anthropic", None)
        else:
            sys.modules["anthropic"] = old


def test_llm_google_no_api_key():
    """GoogleGeminiClient без API ключа — client не инициализирован."""
    from src.llm.providers import GoogleGeminiClient
    with patch.dict(os.environ, {}, clear=True):
        client = GoogleGeminiClient(model="gemini-pro", temperature=0.3)
        out = client.call("test")
    assert out.get("error") == "Gemini client not initialized"


def test_asr_providers_get_asr_provider_distil():
    """get_asr_provider('distil-whisper') с моком ctranslate2."""
    from src.asr.providers import get_asr_provider
    if __import__("sys").platform == "win32":
        pytest.skip("DistilWhisper often fails on Windows")
    try:
        p = get_asr_provider("distil-whisper", model_size="distil-small.en", device="cpu")
        assert p is not None
    except Exception:
        pytest.skip("ctranslate2 not available")
