"""Нагрузочные тесты API endpoints."""
import pytest
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.mark.performance
def test_health_endpoint_load():
    """Проверка производительности /health endpoint под нагрузкой."""
    client = TestClient(app)
    
    # Параметры нагрузки
    num_requests = 100
    num_threads = 10
    
    def make_request():
        start = time.time()
        response = client.get("/health")
        latency = (time.time() - start) * 1000  # в миллисекундах
        return response.status_code, latency
    
    latencies = []
    errors = 0
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(make_request) for _ in range(num_requests)]
        
        for future in as_completed(futures):
            try:
                status_code, latency = future.result()
                if status_code == 200:
                    latencies.append(latency)
                else:
                    errors += 1
            except Exception:
                errors += 1
    
    # Проверяем метрики
    assert errors == 0, f"Ошибок при нагрузке: {errors}"
    assert len(latencies) == num_requests
    
    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    
    # SLA: P95 < 500ms для health endpoint
    assert p95_latency < 500, f"P95 latency {p95_latency}ms превышает SLA (500ms)"
    
    print(f"Average latency: {avg_latency:.2f}ms")
    print(f"P95 latency: {p95_latency:.2f}ms")
    print(f"Errors: {errors}")


@pytest.mark.performance
def test_metrics_endpoint_load():
    """Проверка производительности /metrics endpoint под нагрузкой."""
    client = TestClient(app)
    
    num_requests = 50
    num_threads = 5
    
    def make_request():
        start = time.time()
        response = client.get("/metrics")
        latency = (time.time() - start) * 1000
        return response.status_code, latency
    
    latencies = []
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(make_request) for _ in range(num_requests)]
        
        for future in as_completed(futures):
            status_code, latency = future.result()
            if status_code == 200:
                latencies.append(latency)
    
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    
    # SLA: P95 < 1000ms для metrics endpoint
    assert p95_latency < 1000, f"P95 latency {p95_latency}ms превышает SLA (1000ms)"
