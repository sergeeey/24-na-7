"""Роутер для метрик системы."""
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import Response

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api.metrics")
router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def get_metrics():
    """
    Endpoint для метрик системы (Prometheus-compatible).
    
    Возвращает метрики производительности, состояния и здоровья системы.
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/metrics"
    ```
    
    **Пример ответа:**
    ```json
    {
        "timestamp": "2024-02-17T12:00:00",
        "service": "reflexio",
        "version": "0.1.0",
        "storage": {
            "uploads_count": 10,
            "recordings_count": 5
        },
        "database": {
            "transcriptions_count": 100,
            "facts_count": 50
        }
    }
    ```
    """
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "service": "reflexio",
        "version": "0.1.0",
    }
    
    # Загружаем метрики из cursor-metrics.json если есть
    metrics_file = Path("cursor-metrics.json")
    if metrics_file.exists():
        try:
            file_metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
            metrics.update(file_metrics.get("metrics", {}))
        except Exception:
            pass
    
    # Добавляем метрики из storage
    uploads_path = settings.UPLOADS_PATH
    recordings_path = settings.RECORDINGS_PATH
    
    uploads_count = len(list(uploads_path.glob("*.wav"))) if uploads_path.exists() else 0
    recordings_count = len(list(recordings_path.glob("*.wav"))) if recordings_path.exists() else 0
    
    metrics["storage"] = {
        "uploads_count": uploads_count,
        "recordings_count": recordings_count,
    }
    
    # Проверяем базу данных
    db_path = settings.STORAGE_PATH / "reflexio.db"
    if db_path.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transcriptions")
            transcriptions_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM facts")
            facts_count = cursor.fetchone()[0]
            conn.close()
            
            metrics["database"] = {
                "transcriptions_count": transcriptions_count,
                "facts_count": facts_count,
            }
        except Exception:
            metrics["database"] = {"status": "error"}
    
    # Добавляем метрики конфигурации
    metrics["config"] = {
        "filter_music_enabled": settings.FILTER_MUSIC,
        "extended_metrics_enabled": getattr(settings, "EXTENDED_METRICS", False),
        "edge_auto_upload": settings.EDGE_AUTO_UPLOAD,
    }
    
    logger.info("metrics_requested")
    
    return metrics


@router.get("/prometheus")
async def get_prometheus_metrics_endpoint(request: Request):
    """
    Prometheus-compatible metrics endpoint (v4.1 Enhanced).

    Возвращает comprehensive метрики в формате Prometheus:
    - Core metrics (transcriptions, facts, digests)
    - CoVe metrics (confidence, verification rounds)
    - Fact quality metrics (hallucination rate, citation coverage)
    - Retention metrics (deleted records, errors)
    - ProcessLock metrics (active locks, stale locks)

    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/metrics/prometheus"
    ```

    **Пример ответа:**
    ```
    # HELP reflexio_transcriptions_total Total transcriptions
    # TYPE reflexio_transcriptions_total counter
    reflexio_transcriptions_total 100

    # HELP reflexio_hallucination_rate_24h Hallucination rate (last 24h)
    # TYPE reflexio_hallucination_rate_24h gauge
    reflexio_hallucination_rate_24h 0.0023

    # HELP reflexio_cove_avg_confidence_24h Average CoVe confidence (last 24h)
    # TYPE reflexio_cove_avg_confidence_24h gauge
    reflexio_cove_avg_confidence_24h 0.8542
    ```
    """
    from src.monitoring import get_prometheus_metrics

    try:
        metrics_content = get_prometheus_metrics()
        logger.info("prometheus_metrics_collected")
        return Response(content=metrics_content, media_type="text/plain")
    except Exception as e:
        logger.error(f"prometheus_metrics_collection_failed: {e}")
        # Fallback to basic metrics
        fallback_metrics = [
            "# HELP reflexio_health Health status",
            "# TYPE reflexio_health gauge",
            "reflexio_health 0",
            f"# ERROR {str(e)}"
        ]
        return Response(content="\n".join(fallback_metrics) + "\n", media_type="text/plain")
