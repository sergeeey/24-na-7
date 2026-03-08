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
    # Умеренная нагрузка, чтобы не исчерпать rate limit 200/min для остальных тестов
    num_requests = 50
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


@pytest.mark.performance
def test_health_stress_200_requests():
    """Стресс: 40 запросов к /health (суммарно с др. performance-тестами < 200/min)."""
    client = TestClient(app)
    num_requests = 40
    num_threads = 8

    def make_request():
        start = time.time()
        response = client.get("/health")
        latency = (time.time() - start) * 1000
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

    assert errors == 0, f"Ошибок при стрессе: {errors}"
    assert len(latencies) == num_requests, f"Успешных {len(latencies)} из {num_requests}"
    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
    assert p95_latency < 1000, f"P95 {p95_latency}ms превышает 1000ms при стрессе"
    print(f"Stress: {num_requests} req, avg={avg_latency:.2f}ms, P95={p95_latency:.2f}ms, P99={p99_latency:.2f}ms")
