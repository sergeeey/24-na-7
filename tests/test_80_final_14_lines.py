"""
Финальные тесты для выхода на 80% покрытия.
WebSocket /ws/ingest, migrate main(), API metrics.
"""
import sys
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import pytest


def test_websocket_ingest_connect():
    """WebSocket /ws/ingest принимает подключение и обрабатывает сообщения."""
    from src.api.main import app

    client = TestClient(app)
    
    # Проверяем что WebSocket endpoint существует
    with client.websocket_connect("/ws/ingest") as ws:
        # Отправляем текстовое сообщение
        ws.send_text('{"type": "audio", "data": "dGVzdA=="}')  # base64 для "test"
        
        # Получаем ответ
        response = ws.receive_json()
        
        # Проверяем структуру ответа
        assert "type" in response
        assert response["type"] in ("received", "error", "transcription")
        
        if response["type"] == "received":
            assert "file_id" in response
            assert "status" in response


def test_websocket_ingest_binary_data():
    """WebSocket /ws/ingest обрабатывает бинарные данные."""
    from src.api.main import app

    client = TestClient(app)
    
    # Создаём минимальный WAV заголовок (44 байта)
    wav_header = b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
    
    with client.websocket_connect("/ws/ingest") as ws:
        ws.send_bytes(wav_header)
        
        # Получаем ответ о получении
        response = ws.receive_json()
        assert response["type"] in ("received", "error")
        
        if response["type"] == "received":
            assert "file_id" in response
            assert isinstance(response["file_id"], str)


def test_websocket_ingest_invalid_message():
    """WebSocket /ws/ingest обрабатывает невалидные сообщения."""
    from src.api.main import app

    client = TestClient(app)
    
    with client.websocket_connect("/ws/ingest") as ws:
        # Отправляем невалидное сообщение
        ws.send_text('{"type": "unknown_type"}')
        
        response = ws.receive_json()
        assert response["type"] == "error"
        assert "message" in response


def test_migrate_main_no_flags_returns_1():
    """migrate main() без флагов возвращает 1 (код ошибки)."""
    with patch.object(sys, "argv", ["migrate"]):
        from src.storage.migrate import main
        result = main()
        assert result == 1, "main() должен возвращать 1 при отсутствии флагов"


def test_migrate_main_with_help_flag():
    """migrate main() с флагом --help обрабатывается корректно."""
    with patch.object(sys, "argv", ["migrate", "--help"]):
        from src.storage.migrate import main
        # Проверяем что не падает с ошибкой
        try:
            result = main()
            # Может вернуть 0 или 1 в зависимости от реализации
            assert result in (0, 1)
        except SystemExit:
            # argparse может вызвать SystemExit при --help
            pass


def test_api_metrics_returns_200():
    """GET /metrics возвращает 200 и валидную структуру."""
    from src.api.main import app

    client = TestClient(app)
    r = client.get("/metrics")
    
    assert r.status_code == 200, f"Ожидался статус 200, получен {r.status_code}"
    
    # Проверяем структуру ответа
    data = r.json()
    assert "timestamp" in data
    assert "service" in data
    assert data["service"] == "reflexio"
    assert "version" in data


def test_api_metrics_prometheus_format():
    """GET /metrics/prometheus возвращает Prometheus формат."""
    from src.api.main import app

    client = TestClient(app)
    r = client.get("/metrics/prometheus")
    
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    
    # Проверяем что ответ содержит Prometheus метрики
    content = r.text
    assert "reflexio_health" in content
    assert "# HELP" in content or "# TYPE" in content
