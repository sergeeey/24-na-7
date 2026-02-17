"""
Тесты для доведения покрытия api/main до 80%.
Startup, 404, форматы ответов.
"""
from unittest.mock import patch
from fastapi.testclient import TestClient


def test_app_health_returns_ok():
    """GET /health возвращает 200 и status ok."""
    from src.api.main import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


def test_app_nonexistent_returns_404():
    """GET несуществующего пути возвращает 404."""
    from src.api.main import app

    client = TestClient(app)
    r = client.get("/nonexistent-path-xyz")
    assert r.status_code == 404


def test_app_startup_health_monitor_exception():
    """Старт приложения: при ошибке запуска health monitor логируется предупреждение."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    with patch("asyncio.create_task", side_effect=Exception("task failed")):
        client = TestClient(app)
        resp = client.get("/health")
    assert resp.status_code == 200


def test_app_root_returns_endpoints():
    """GET / возвращает список эндпоинтов."""
    from src.api.main import app

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "endpoints" in data
    assert "health" in data.get("endpoints", {})


def test_metrics_with_invalid_cursor_metrics_json(tmp_path, monkeypatch):
    """GET /metrics при невалидном cursor-metrics.json не падает, исключение перехватывается."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    (tmp_path / "cursor-metrics.json").write_text("not valid json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200


def test_digest_date_generation_exception():
    """GET /digest/{date} при исключении генератора возвращает 500."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    with patch("src.api.main.DigestGenerator") as mock_cls:
        mock_cls.return_value.generate.side_effect = RuntimeError("generate failed")
        client = TestClient(app)
        r = client.get("/digest/2025-01-15?format=markdown")
    assert r.status_code == 500
    assert "Failed to generate" in r.json().get("detail", "")


def test_digest_today_generation_exception():
    """GET /digest/today при исключении генератора возвращает 500."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    with patch("src.api.main.DigestGenerator") as mock_cls:
        mock_cls.return_value.generate.side_effect = RuntimeError("today failed")
        client = TestClient(app)
        r = client.get("/digest/today?format=markdown")
    assert r.status_code == 500


def test_density_analysis_exception():
    """GET /digest/{date}/density при исключении анализатора возвращает 500."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    with patch("src.api.main.InformationDensityAnalyzer") as mock_cls:
        mock_cls.return_value.analyze_day.side_effect = RuntimeError("analyze failed")
        client = TestClient(app)
        r = client.get("/digest/2025-01-01/density")
    assert r.status_code == 500


def test_audio_upload_save_exception():
    """POST /ingest/audio при ошибке сохранения файла возвращает 500."""
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.utils.config import settings

    child = MagicMock()
    child.write_bytes.side_effect = OSError("disk full")
    fake_path = MagicMock()
    fake_path.__truediv__.return_value = child
    with patch.object(settings, "UPLOADS_PATH", fake_path):
        client = TestClient(app)
        r = client.post("/ingest/audio", files={"file": ("x.wav", b"fake", "audio/wav")})
    assert r.status_code == 500
    assert "Failed to save" in r.json().get("detail", "")
