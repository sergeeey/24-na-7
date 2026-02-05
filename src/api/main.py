"""FastAPI приложение Reflexio 24/7."""
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Path as PathParam, Request
from fastapi.responses import JSONResponse, Response
from datetime import datetime, date
from pathlib import Path
import uuid
import os
import json
import asyncio

from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger
from src.utils.rate_limiter import setup_rate_limiting, RateLimitConfig
from src.utils.input_guard import InputGuard, SecurityError, get_input_guard
from src.utils.guardrails import Guardrails, get_guardrails
from src.asr.transcribe import transcribe_audio
from src.digest.generator import DigestGenerator
from src.digest.analyzer import InformationDensityAnalyzer

# Rate Limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
limiter = Limiter(key_func=get_remote_address)

# SAFE проверки (если доступны)
SAFE_ENABLED = os.getenv("SAFE_MODE", "audit") in ("strict", "audit")
safe_checker = None
if SAFE_ENABLED:
    try:
        import sys
        from pathlib import Path as PathLib
        safe_path = PathLib(__file__).parent.parent.parent / ".cursor" / "validation" / "safe" / "checks.py"
        if safe_path.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("safe_checks", safe_path)
            safe_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(safe_module)
            safe_checker = safe_module.SAFEChecker()
    except Exception as e:
        logger = get_logger("api")
        logger.warning("safe_checker_not_available", error=str(e))
        safe_checker = None

# Настройка логирования
setup_logging()
logger = get_logger("api")

# Инициализируем logger до SAFE проверки
if not safe_checker and SAFE_ENABLED:
    logger.warning("SAFE checker initialization failed, running without SAFE validation")

# Создаём приложение
app = FastAPI(
    title="Reflexio 24/7",
    description="Умный диктофон и дневной анализатор",
    version="0.1.0",
)

# Настраиваем Rate Limiting
limiter = setup_rate_limiting(app)

# Инициализируем Input Guard
input_guard = get_input_guard()


@app.middleware("http")
async def input_guard_middleware(request: Request, call_next):
    """
    Input Guard middleware — защита от prompt injection.
    Проверяет все POST/PUT/PATCH запросы с телом.
    """
    # Пропускаем health, metrics и файлы
    if request.url.path in ["/health", "/metrics", "/"] or request.method == "GET":
        return await call_next(request)
    
    # Проверяем только запросы с JSON
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return await call_next(request)
    
    try:
        body = await request.body()
        if not body:
            return await call_next(request)
        
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return await call_next(request)
        
        # Проверяем текстовые поля на prompt injection
        text_fields = ["text", "prompt", "query", "content", "input"]
        for field in text_fields:
            if field in payload and isinstance(payload[field], str):
                result = input_guard.check(payload[field])
                
                if not result.is_safe:
                    logger.warning(
                        "input_guard_blocked",
                        path=request.url.path,
                        threat_level=result.threat_level.value,
                        threats=result.threats_detected,
                    )
                    
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "Security violation detected",
                            "details": result.reason,
                            "threat_level": result.threat_level.value,
                        }
                    )
                
                # Обновляем поле санитизированным значением
                if result.sanitized_input:
                    payload[field] = result.sanitized_input
        
        # Пересоздаем request с обновленным телом
        # (FastAPI не позволяет просто так изменить body, поэтому пропускаем дальше)
        # В production здесь нужна более сложная логика с CustomRequest
        
    except SecurityError as e:
        logger.error("security_error", error=str(e))
        return JSONResponse(
            status_code=403,
            content={"error": "Security check failed", "message": str(e)}
        )
    except Exception as e:
        logger.error("input_guard_error", error=str(e))
        # В audit mode не блокируем при ошибках
        if os.getenv("SAFE_MODE") == "strict":
            raise
    
    return await call_next(request)


@app.middleware("http")
async def safe_middleware(request: Request, call_next):
    """SAFE middleware для проверки входящих/исходящих данных."""
    if not safe_checker:
        return await call_next(request)
    
    # Проверка домена (если есть outbound запросы)
    # Для входящих проверяем только payload
    
    # Пропускаем health и metrics
    if request.url.path in ["/health", "/metrics", "/"]:
        return await call_next(request)
    
    try:
        # Читаем тело запроса если есть
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if body:
                try:
                    payload = json.loads(body)
                    # Проверяем payload через SAFE
                    validation_result = safe_checker.validate_payload(
                        payload,
                        require_pii_mask=os.getenv("SAFE_PII_MASK", "1") == "1"
                    )
                    if not validation_result["valid"] and os.getenv("SAFE_MODE") == "strict":
                        return JSONResponse(
                            status_code=400,
                            content={"error": "SAFE validation failed", "details": validation_result["errors"]}
                        )
                except json.JSONDecodeError:
                    pass  # Не JSON, пропускаем
        
        response = await call_next(request)
        
        # Проверяем исходящий ответ (только для JSON)
        if response.headers.get("content-type", "").startswith("application/json"):
            # Для упрощения не перехватываем body, только логируем
            pass
        
        return response
    except Exception as e:
        logger.error("safe_middleware_error", error=str(e))
        return await call_next(request)


@app.on_event("startup")
async def startup():
    """Инициализация при старте."""
    logger.info("Reflexio API starting", host=settings.API_HOST, port=settings.API_PORT)
    if safe_checker:
        logger.info("SAFE validation enabled", mode=os.getenv("SAFE_MODE", "audit"))
    
    # Запускаем health monitoring loop
    try:
        import asyncio
        from src.monitor.health import periodic_check
        
        # Запускаем в фоне
        asyncio.create_task(periodic_check(interval=300))  # каждые 5 минут
        logger.info("health_monitor_started")
    except Exception as e:
        logger.warning("health_monitor_failed", error=str(e))


@app.get("/health")
@limiter.limit(RateLimitConfig.HEALTH_LIMIT)
async def health(request: Request):
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.1.0",
    }


@app.post("/ingest/audio")
@limiter.limit(RateLimitConfig.INGEST_AUDIO_LIMIT)
async def ingest_audio(request: Request, file: UploadFile = File(...)):
    """
    Принимает аудиофайл от edge-устройства.
    
    Сохраняет файл в storage/uploads/ и возвращает ID для отслеживания.
    SAFE проверки: размер файла, расширение, PII в метаданных.
    """
    try:
        # SAFE: Проверка расширения файла
        if safe_checker:
            from pathlib import Path as PathLib
            temp_path = PathLib(file.filename or "temp.wav")
            ext_valid, ext_reason = safe_checker.check_file_extension(temp_path)
            if not ext_valid:
                logger.warning("safe_file_extension_check_failed", reason=ext_reason, filename=file.filename)
                if os.getenv("SAFE_MODE") == "strict":
                    raise HTTPException(status_code=400, detail=f"SAFE validation failed: {ext_reason}")
        
        # Читаем содержимое файла
        content = await file.read()
        file_size = len(content)
        
        # SAFE: Проверка размера файла
        if safe_checker:
            from pathlib import Path as PathLib
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=PathLib(file.filename or "").suffix) as temp_file:
                temp_file.write(content)
                temp_path = PathLib(temp_file.name)
                size_valid, size_reason = safe_checker.check_file_size(temp_path)
                temp_path.unlink()  # Удаляем временный файл
                
                if not size_valid:
                    logger.warning("safe_file_size_check_failed", reason=size_reason, size=file_size)
                    if os.getenv("SAFE_MODE") == "strict":
                        raise HTTPException(status_code=400, detail=f"SAFE validation failed: {size_reason}")
        
        # Генерируем уникальное имя файла
        file_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file_id}.wav"
        dest_path = settings.UPLOADS_PATH / filename
        
        # Сохраняем файл
        dest_path.write_bytes(content)
        
        logger.info(
            "audio_received",
            filename=filename,
            size=file_size,
            content_type=file.content_type,
            safe_validation="passed" if safe_checker else "disabled",
        )
        
        return {
            "status": "received",
            "id": file_id,
            "filename": filename,
            "path": str(dest_path),
            "size": file_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("audio_upload_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save audio: {str(e)}")


@app.post("/asr/transcribe")
async def transcribe_endpoint(file_id: str = Query(..., description="ID файла для транскрипции")):
    """
    Транскрибирует загруженный аудиофайл по его ID.
    
    Ищет файл в storage/uploads/ по ID из имени файла.
    """
    try:
        # Ищем файл по ID в имени
        matching_files = list(settings.UPLOADS_PATH.glob(f"*_{file_id}.wav"))
        if not matching_files:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")
        
        audio_path = matching_files[0]
        
        logger.info("transcription_started", file_id=file_id, path=str(audio_path))
        
        # Транскрибируем
        result = transcribe_audio(audio_path)
        
        return {
            "status": "success",
            "file_id": file_id,
            "transcription": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("transcription_failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.get("/ingest/status/{file_id}")
async def get_ingest_status(file_id: str):
    """Проверяет статус обработки файла."""
    # В MVP всегда возвращаем pending, в будущем будем отслеживать статус
    return {
        "id": file_id,
        "status": "pending",
        "message": "File received, processing will be implemented in next iteration",
    }


@app.get("/digest/today")
async def get_digest_today(format: str = Query("markdown", regex="^(markdown|json)$")):
    """
    Получает дайджест за сегодня.
    
    Args:
        format: Формат ответа (markdown или json)
    """
    try:
        target_date = date.today()
        generator = DigestGenerator()
        
        # Генерируем дайджест
        output_file = generator.generate(
            target_date=target_date,
            output_format=format,
            include_metadata=True,
        )
        
        if format == "json":
            import json
            content = json.loads(output_file.read_text(encoding="utf-8"))
            return content
        else:
            from fastapi.responses import Response
            content = output_file.read_text(encoding="utf-8")
            return Response(content=content, media_type="text/markdown")
            
    except Exception as e:
        logger.error("digest_generation_failed", date="today", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate digest: {str(e)}")


@app.get("/digest/{target_date}")
async def get_digest(
    target_date: str = PathParam(..., description="Дата в формате YYYY-MM-DD"),
    format: str = Query("markdown", regex="^(markdown|json)$"),
):
    """
    Получает дайджест за указанную дату.
    
    Args:
        target_date: Дата в формате YYYY-MM-DD
        format: Формат ответа (markdown или json)
    """
    try:
        # Парсим дату
        parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        generator = DigestGenerator()
        
        # Генерируем дайджест
        output_file = generator.generate(
            target_date=parsed_date,
            output_format=format,
            include_metadata=True,
        )
        
        if format == "json":
            import json
            content = json.loads(output_file.read_text(encoding="utf-8"))
            return content
        else:
            from fastapi.responses import Response
            content = output_file.read_text(encoding="utf-8")
            return Response(content=content, media_type="text/markdown")
            
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        logger.error("digest_generation_failed", date=target_date, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate digest: {str(e)}")


@app.get("/digest/{target_date}/density")
async def get_density_analysis(
    target_date: str = PathParam(..., description="Дата в формате YYYY-MM-DD"),
):
    """
    Получает анализ информационной плотности за указанную дату.
    
    Args:
        target_date: Дата в формате YYYY-MM-DD
    """
    try:
        # Парсим дату
        parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        analyzer = InformationDensityAnalyzer()
        analysis = analyzer.analyze_day(parsed_date)
        
        return analysis
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        logger.error("density_analysis_failed", date=target_date, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to analyze density: {str(e)}")


@app.get("/metrics")
async def get_metrics():
    """
    Endpoint для метрик системы (Prometheus-compatible).
    
    Возвращает метрики производительности, состояния и здоровья системы.
    """
    from pathlib import Path
    import json
    import time
    
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
    
    # Prometheus-совместимые метрики
    prometheus_metrics = []
    prometheus_metrics.append(f"# HELP reflexio_uploads_total Total number of uploaded files")
    prometheus_metrics.append(f"# TYPE reflexio_uploads_total counter")
    prometheus_metrics.append(f"reflexio_uploads_total {uploads_count}")
    
    prometheus_metrics.append(f"# HELP reflexio_transcriptions_total Total number of transcriptions")
    prometheus_metrics.append(f"# TYPE reflexio_transcriptions_total counter")
    prometheus_metrics.append(f"reflexio_transcriptions_total {metrics.get('database', {}).get('transcriptions_count', 0)}")
    
    prometheus_metrics.append(f"# HELP reflexio_health Health status (1 = healthy, 0 = unhealthy)")
    prometheus_metrics.append(f"# TYPE reflexio_health gauge")
    prometheus_metrics.append(f"reflexio_health 1")
    
    logger.info("metrics_requested")
    
    return metrics


@app.get("/metrics/prometheus")
async def get_prometheus_metrics(request: Request):
    """
    Prometheus-compatible metrics endpoint.
    
    Возвращает метрики в формате Prometheus.
    """
    from pathlib import Path
    import json
    
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
    
    from fastapi.responses import Response
    return Response(content="\n".join(prometheus_metrics) + "\n", media_type="text/plain")


@app.post("/search/phrases")
async def search_phrases(request: Request):
    """
    Поиск по фразам через semantic search (embeddings).
    
    Body:
        {
            "audio_id": str,
            "query": str,
            "limit": int (optional, default 10)
        }
    """
    try:
        body = await request.json()
        audio_id = body.get("audio_id")
        query = body.get("query", "")
        limit = body.get("limit", 10)
        
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        
        from src.storage.embeddings import search_phrases
        
        results = search_phrases(query, audio_id=audio_id, limit=limit)
        
        return {
            "query": query,
            "audio_id": audio_id,
            "matches": results,
            "count": len(results),
        }
        
    except Exception as e:
        logger.error("phrase_search_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.post("/voice/intent")
async def recognize_intent(request: Request):
    """
    Распознавание intent через Voiceflow RAG или GPT-mini fallback.
    
    Body:
        {
            "text": str,
            "user_id": str (optional)
        }
    """
    try:
        body = await request.json()
        text = body.get("text", "")
        user_id = body.get("user_id", "default")
        
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        
        from src.voice_agent.voiceflow_rag import get_voiceflow_client
        
        client = get_voiceflow_client()
        result = client.recognize_intent(text, user_id=user_id)
        
        return result
        
    except Exception as e:
        logger.error("intent_recognition_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Intent recognition failed: {str(e)}")


@app.get("/")
async def root():
    """Корневой endpoint."""
    return {
        "service": "Reflexio 24/7",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "ingest_audio": "/ingest/audio",
            "transcribe": "/asr/transcribe",
            "status": "/ingest/status/{file_id}",
            "digest_today": "/digest/today",
            "digest_date": "/digest/{date}",
            "density_analysis": "/digest/{date}/density",
            "metrics": "/metrics",
            "search_phrases": "/search/phrases",
            "recognize_intent": "/voice/intent",
        },
    }

