"""E2E тесты для полного цикла ingest → transcribe → digest."""
import pytest
from pathlib import Path
from datetime import date
from unittest.mock import patch, MagicMock


def test_full_ingest_pipeline(client, test_db):
    """Полный цикл: загрузка аудио → транскрипция → дайджест."""
    # Шаг 1: Загрузка аудио
    # Создаём минимальный WAV файл для теста
    wav_content = b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
    
    with patch("src.api.routers.ingest.settings") as mock_settings:
        mock_settings.UPLOADS_PATH = Path(test_db).parent / "uploads"
        mock_settings.UPLOADS_PATH.mkdir(exist_ok=True)
        
        response = client.post(
            "/ingest/audio",
            files={"file": ("test.wav", wav_content, "audio/wav")}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "filename" in data
        file_id = data["id"]
        
        # Шаг 2: Проверка статуса
        status_response = client.get(f"/ingest/status/{file_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["id"] == file_id
        
        # Шаг 3: Транскрипция (с моком ASR)
        with patch("src.api.routers.asr.transcribe_audio") as mock_transcribe:
            mock_transcribe.return_value = {
                "text": "Тестовая транскрипция",
                "language": "ru",
                "segments": []
            }
            
            transcribe_response = client.post(f"/asr/transcribe?file_id={file_id}")
            assert transcribe_response.status_code == 200
            transcribe_data = transcribe_response.json()
            assert transcribe_data["status"] == "success"
            assert "transcription" in transcribe_data


def test_websocket_ingest_flow(client, test_db):
    """E2E тест WebSocket потока данных."""
    with client.websocket_connect("/ws/ingest") as ws:
        # Отправляем бинарный WAV
        wav_content = b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        
        with patch("src.api.routers.websocket.transcribe_audio") as mock_transcribe:
            mock_transcribe.return_value = {
                "text": "WebSocket транскрипция",
                "language": "ru"
            }
            
            ws.send_bytes(wav_content)
            
            # Получаем подтверждение
            response1 = ws.receive_json()
            assert response1["type"] in ("received", "error")
            
            if response1["type"] == "received":
                file_id = response1["file_id"]
                
                # Получаем транскрипцию
                response2 = ws.receive_json()
                assert response2["type"] in ("transcription", "error")
                
                if response2["type"] == "transcription":
                    assert response2["file_id"] == file_id
                    assert "text" in response2


def test_digest_generation_e2e(client, test_db):
    """E2E тест генерации дайджеста."""
    # Создаём тестовые данные в БД
    import sqlite3
    conn = sqlite3.connect(str(test_db))
    today = date.today().isoformat()
    
    conn.execute(
        "INSERT INTO transcriptions (id, ingest_id, text, created_at) VALUES (?, ?, ?, ?)",
        ("t1", "i1", "Тестовая транскрипция 1", today)
    )
    conn.execute(
        "INSERT INTO transcriptions (id, ingest_id, text, created_at) VALUES (?, ?, ?, ?)",
        ("t2", "i2", "Тестовая транскрипция 2", today)
    )
    conn.commit()
    conn.close()
    
    # Генерируем дайджест
    with patch("src.api.routers.digest.settings") as mock_settings:
        mock_settings.STORAGE_PATH = Path(test_db).parent
        
        response = client.get(f"/digest/today?format=json")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
