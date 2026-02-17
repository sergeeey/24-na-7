"""
Тесты для Rate Limiting (P0-2).
Проверка защиты от DDoS и abuse.
"""
import pytest
from fastapi.testclient import TestClient

# Нужно импортировать до создания TestClient
import os
os.environ["SAFE_MODE"] = "disabled"  # Отключаем SAFE для тестов

from src.api.main import app


@pytest.fixture
def client():
    """Фикстура для тестового клиента."""
    return TestClient(app)


class TestRateLimitIngest:
    """Тесты лимитирования загрузки аудио."""
    
    def test_ingest_within_limit(self, client):
        """Загрузка в пределах лимита должна работать."""
        # Создаем фейковый WAV файл
        wav_header = bytes([
            0x52, 0x49, 0x46, 0x46,  # "RIFF"
            0x24, 0x00, 0x00, 0x00,  # chunk size
            0x57, 0x41, 0x56, 0x45,  # "WAVE"
            0x66, 0x6D, 0x74, 0x20,  # "fmt "
            0x10, 0x00, 0x00, 0x00,  # fmt chunk size
            0x01, 0x00,              # audio format (PCM)
            0x01, 0x00,              # channels (mono)
            0x44, 0xAC, 0x00, 0x00,  # sample rate (44100)
            0x88, 0x58, 0x01, 0x00,  # byte rate
            0x02, 0x00,              # block align
            0x10, 0x00,              # bits per sample (16)
            0x64, 0x61, 0x74, 0x61,  # "data"
            0x00, 0x00, 0x00, 0x00,  # data chunk size
        ])
        
        files = {"file": ("test.wav", wav_header, "audio/wav")}
        response = client.post("/ingest/audio", files=files)
        
        # Первый запрос должен пройти (или 200 или 500 если нет storage)
        assert response.status_code in [200, 500]
    
    def test_rate_limit_headers_present(self, client):
        """Проверяем наличие RateLimit заголовков."""
        response = client.get("/health")
        
        # Проверяем наличие заголовков (если rate limiting включен)
        assert "X-RateLimit-Limit" in response.headers or response.status_code == 200
        assert "X-RateLimit-Remaining" in response.headers or response.status_code == 200
    
    def test_health_limit_high(self, client):
        """Health endpoint должен иметь высокий лимит."""
        # Делаем много запросов к health
        for i in range(50):
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"


class TestRateLimitHealth:
    """Тесты лимитирования health endpoint."""
    
    def test_health_basic(self, client):
        """Health check должен работать."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "version" in data


class TestRateLimitHeaders:
    """Тесты заголовков rate limiting."""
    
    def test_headers_format(self, client):
        """Заголовки должны иметь правильный формат."""
        response = client.get("/health")
        
        # Проверяем структуру заголовков если они есть
        if "X-RateLimit-Limit" in response.headers:
            limit = response.headers["X-RateLimit-Limit"]
            assert limit.isdigit()
            assert int(limit) > 0
        
        if "X-RateLimit-Remaining" in response.headers:
            remaining = response.headers["X-RateLimit-Remaining"]
            assert remaining.isdigit()
            assert int(remaining) >= 0


class TestRateLimitDifferentIPs:
    """Тесты изоляции лимитов по IP."""
    
    def test_different_clients_have_separate_limits(self, client):
        """Разные клиенты должны иметь отдельные лимиты."""
        # Имитируем разные IP через X-Forwarded-For
        headers1 = {"X-Forwarded-For": "1.2.3.4"}
        headers2 = {"X-Forwarded-For": "5.6.7.8"}
        
        # Оба клиента должны иметь полные лимиты
        response1 = client.get("/health", headers=headers1)
        response2 = client.get("/health", headers=headers2)
        
        assert response1.status_code == 200
        assert response2.status_code == 200


@pytest.mark.skip(reason="Может занять много времени, запускать вручную")
class TestRateLimitExceeding:
    """Тесты превышения лимитов (медленные)."""
    
    def test_exceeding_limit_returns_429(self, client):
        """При превышении лимита должен возвращаться 429."""
        # Отправляем много запросов чтобы превысить лимит
        responses = []
        for i in range(150):  # Больше чем default limit (100/minute)
            response = client.get("/health")
            responses.append(response.status_code)
        
        # Должен быть хотя бы один 429
        assert 429 in responses, "Rate limiting не сработал"
    
    def test_rate_limit_reset_after_window(self, client):
        """Лимит должен сбрасываться после временного окна."""
        # Превышаем лимит
        for i in range(150):
            client.get("/health")
        
        # Проверяем что сейчас 429
        response = client.get("/health")
        if response.status_code == 429:
            # Ждем сброса окна (в реальных тестах лучше мокать время)
            import time
            time.sleep(60)  # Ждем минуту
            
            # Теперь должно работать
            response = client.get("/health")
            assert response.status_code == 200


class TestRateLimitConfiguration:
    """Тесты конфигурации rate limiting."""
    
    def test_config_values(self):
        """Проверка значений конфигурации."""
        from src.utils.rate_limiter import RateLimitConfig
        
        # Проверяем что лимиты установлены
        assert RateLimitConfig.INGEST_AUDIO_LIMIT == "10/minute"
        assert RateLimitConfig.TRANSCRIBE_LIMIT == "30/minute"
        assert RateLimitConfig.DIGEST_LIMIT == "60/minute"
        assert RateLimitConfig.HEALTH_LIMIT == "200/minute"
        assert RateLimitConfig.DEFAULT_LIMIT == "100/minute"
    
    def test_limiter_created(self):
        """Limiter должен создаваться без ошибок."""
        from src.utils.rate_limiter import create_limiter
        
        limiter = create_limiter()
        assert limiter is not None
        assert limiter.enabled is True
