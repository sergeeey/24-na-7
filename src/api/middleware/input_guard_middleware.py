"""Input Guard middleware — защита от prompt injection."""
import json
import os
from fastapi import Request
from fastapi.responses import JSONResponse

from src.utils.input_guard import SecurityError, get_input_guard
from src.utils.logging import get_logger

logger = get_logger("api.middleware")
input_guard = get_input_guard()


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
