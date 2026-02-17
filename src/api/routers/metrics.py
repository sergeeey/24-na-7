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
async def get_prometheus_metrics(request: Request):
    """
    Prometheus-compatible metrics endpoint.
    
    Возвращает метрики в формате Prometheus.
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/metrics/prometheus"
    ```
    
    **Пример ответа:**
    ```
    # HELP reflexio_uploads_total Total number of uploaded files
    # TYPE reflexio_uploads_total counter
    reflexio_uploads_total 10
    
    # HELP reflexio_transcriptions_total Total number of transcriptions
    # TYPE reflexio_transcriptions_total counter
    reflexio_transcriptions_total 100
    ```
    """
    prometheus_metrics = []
    
    # Базовые метрики
    uploads_path = settings.UPLOADS_PATH
    uploads_count = len(list(uploads_path.glob("*.wav"))) if uploads_path.exists() else 0
    
    prometheus_metrics.append("# HELP reflexio_uploads_total Total number of uploaded files")
    prometheus_metrics.append("# TYPE reflexio_uploads_total counter")
    prometheus_metrics.append(f"reflexio_uploads_total {uploads_count}")
    
    # Метрики из БД
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
            
            prometheus_metrics.append("# HELP reflexio_transcriptions_total Total number of transcriptions")
            prometheus_metrics.append("# TYPE reflexio_transcriptions_total counter")
            prometheus_metrics.append(f"reflexio_transcriptions_total {transcriptions_count}")
            
            prometheus_metrics.append("# HELP reflexio_facts_total Total number of facts")
            prometheus_metrics.append("# TYPE reflexio_facts_total counter")
            prometheus_metrics.append(f"reflexio_facts_total {facts_count}")
        except Exception:
            pass
    
    # Health метрика
    prometheus_metrics.append("# HELP reflexio_health Health status (1 = healthy, 0 = unhealthy)")
    prometheus_metrics.append("# TYPE reflexio_health gauge")
    prometheus_metrics.append("reflexio_health 1")
    
    # Метрики из cursor-metrics.json
    metrics_file = Path("cursor-metrics.json")
    if metrics_file.exists():
        try:
            file_metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
            osint_metrics = file_metrics.get("metrics", {}).get("osint", {})
            if osint_metrics.get("avg_deepconf_confidence") is not None:
                prometheus_metrics.append("# HELP reflexio_deepconf_avg_confidence Average DeepConf confidence")
                prometheus_metrics.append("# TYPE reflexio_deepconf_avg_confidence gauge")
                prometheus_metrics.append(f"reflexio_deepconf_avg_confidence {osint_metrics['avg_deepconf_confidence']}")
        except Exception:
            pass
    
    return Response(content="\n".join(prometheus_metrics) + "\n", media_type="text/plain")
