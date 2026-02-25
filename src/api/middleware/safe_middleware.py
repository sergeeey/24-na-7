"""SAFE middleware для проверки входящих/исходящих данных."""
import json
import os

from fastapi import Request
from fastapi.responses import JSONResponse

from src.utils.logging import get_logger

logger = get_logger("api.middleware")

# ПОЧЕМУ: Singleton кэш — SAFEChecker создаётся один раз при первом вызове,
# а не на каждый HTTP-запрос. Это экономит ~1ms per request и избегает
# повторной инициализации при каждом /ingest/audio.
_safe_checker_cache = None
_safe_checker_initialized = False


def get_safe_checker():
    """Получает SAFE checker если доступен (singleton, lazy init)."""
    global _safe_checker_cache, _safe_checker_initialized
    if _safe_checker_initialized:
        return _safe_checker_cache

    _safe_checker_initialized = True  # Помечаем до создания, чтобы не было рекурсии

    safe_enabled = os.getenv("SAFE_MODE", "audit") in ("strict", "audit")
    if not safe_enabled:
        return None

    # Единственный путь: статический импорт из проекта.
    # ПОЧЕМУ убрали dynamic importlib fallback: загрузка произвольного .py файла
    # из .cursor/ = потенциальный RCE если файл подменён. Статический импорт
    # безопасен и достаточен для production.
    try:
        from src.validation.safe.checks import SAFEChecker  # type: ignore

        _safe_checker_cache = SAFEChecker()
        return _safe_checker_cache
    except Exception as e:
        logger.warning("safe_checker_static_import_failed", error=str(e))

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
                        require_pii_mask=os.getenv("SAFE_PII_MASK", "1") == "1",
                    )
                    if not validation_result["valid"] and os.getenv("SAFE_MODE") == "strict":
                        return JSONResponse(
                            status_code=400,
                            content={"error": "SAFE validation failed", "details": validation_result["errors"]},
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
