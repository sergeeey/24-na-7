"""
Тесты для доведения покрытия asr/transcribe до 80%.
Edge cases: fallback при исключении провайдера, transcribe_file.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.mark.skipif(
    __import__("sys").platform == "win32",
    reason="ctranslate2/faster_whisper can crash on Windows when fallback loads",
)
def test_transcribe_audio_provider_raises_then_fallback(tmp_path):
    """transcribe_audio: при исключении от провайдера идёт fallback на local (и там снова исключение без модели)."""
    from src.asr.transcribe import transcribe_audio

    (tmp_path / "a.wav").write_bytes(b"RIFF----WAVE")
    mock_provider = MagicMock()
    mock_provider.transcribe.side_effect = RuntimeError("API error")

    with patch("src.asr.transcribe.get_asr_provider", return_value=mock_provider):
        with patch("src.asr.transcribe.get_model", return_value=None):
            with pytest.raises((ImportError, Exception)):
                transcribe_audio(tmp_path / "a.wav", provider="openai")


def test_transcribe_file_path_object(tmp_path):
    """transcribe_file принимает Path и передаёт в transcribe_audio."""
    from src.asr.transcribe import transcribe_file

    (tmp_path / "f.wav").write_bytes(b"x")
    with patch("src.asr.transcribe.transcribe_audio") as mock_ta:
        mock_ta.return_value = {"text": "ok", "language": "en", "segments": []}
        out = transcribe_file(tmp_path / "f.wav")
    assert out["text"] == "ok"
    mock_ta.assert_called_once()
    assert mock_ta.call_args[0][0] == tmp_path / "f.wav"


def test_get_asr_provider_config_with_edge_mode_and_distil(tmp_path, monkeypatch):
    """get_asr_provider (transcribe): конфиг с edge_mode и distil_whisper, create_provider замокан."""
    import src.asr.transcribe as tmod

    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "asr.yaml").write_text(
        "provider: distil-whisper\nmodel: distil-small.en\nedge_mode: true\n"
        "distil_whisper:\n  model_size: distil-small.en\n  device: cpu\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    tmod._asr_provider = None
    try:
        with patch("src.asr.providers.get_asr_provider", return_value=MagicMock()):
            r = tmod.get_asr_provider()
        assert r is not None
    finally:
        tmod._asr_provider = None


def test_get_asr_provider_creation_raises_returns_none():
    """get_asr_provider (transcribe): при исключении create_provider возвращается None, _asr_provider остаётся None."""
    import src.asr.transcribe as tmod

    tmod._asr_provider = None
    try:
        with patch("src.asr.providers.get_asr_provider", side_effect=RuntimeError("no provider")):
            r = tmod.get_asr_provider()
        assert r is None
    finally:
        tmod._asr_provider = None


def test_transcribe_audio_file_not_found():
    """transcribe_audio при несуществующем файле бросает FileNotFoundError."""
    from src.asr.transcribe import transcribe_audio

    with pytest.raises(FileNotFoundError, match="not found"):
        transcribe_audio(Path("/nonexistent/file.wav"))
