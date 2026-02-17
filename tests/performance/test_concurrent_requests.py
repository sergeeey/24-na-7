"""Тесты конкурентных запросов."""
import pytest
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.mark.performance
def test_concurrent_health_requests():
    """Проверка обработки конкурентных запросов к /health."""
    client = TestClient(app)
    
    num_concurrent = 20
    
    def make_request():
        return client.get("/health")
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        futures = [executor.submit(make_request) for _ in range(num_concurrent)]
        results = [future.result() for future in as_completed(futures)]
    
    total_time = (time.time() - start_time) * 1000
    
    # Все запросы должны быть успешными
    assert all(r.status_code == 200 for r in results)
    
    # Среднее время на запрос должно быть разумным
    avg_time_per_request = total_time / num_concurrent
    assert avg_time_per_request < 100, f"Average time per request {avg_time_per_request}ms слишком высокое"
    
    print(f"Total time for {num_concurrent} concurrent requests: {total_time:.2f}ms")
    print(f"Average time per request: {avg_time_per_request:.2f}ms")
