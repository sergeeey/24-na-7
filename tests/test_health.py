"""Тесты health endpoint."""
from fastapi.testclient import TestClient
from src.api.main import app


def test_health():
    """Проверяет health endpoint."""
    client = TestClient(app)
    resp = client.get("/health")
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["version"] == "0.2.0"


def test_root():
    """Проверяет корневой endpoint."""
    client = TestClient(app)
    resp = client.get("/")
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "Reflexio 24/7"
    assert "endpoints" in data

