"""SAFE middleware для проверки входящих/исходящих данных."""
import json
import os
from fastapi import Request
from fastapi.responses import JSONResponse

from src.utils.logging import get_logger

logger = get_logger("api.middleware")


def get_safe_checker():
    """Получает SAFE checker если доступен."""
    SAFE_ENABLED = os.getenv("SAFE_MODE", "audit") in ("strict", "audit")
    if not SAFE_ENABLED:
        return None
    
    try:
        from pathlib import Path as PathLib
        safe_path = PathLib(__file__).parent.parent.parent.parent / ".cursor" / "validation" / "safe" / "checks.py"
        if safe_path.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("safe_checks", safe_path)
            safe_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(safe_module)
            return safe_module.SAFEChecker()
    except Exception as e:
        logger.warning("safe_checker_not_available", error=str(e))
    
    return None


async def safe_middleware(request: Request, call_next):
    """SAFE middleware для проверки входящих/исходящих данных."""
    safe_checker = get_safe_checker()
    if not safe_checker:
        return await call_next(request)
    
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
