"""API Key authentication middleware.

ПОЧЕМУ middleware а не Depends(): middleware покрывает ВСЕ endpoints разом,
включая будущие. Depends() легко забыть добавить на новый роутер.
"""
import secrets

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("api.auth")

# Paths that don't require authentication
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


def _verify_key(provided: str | None) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    if not settings.API_KEY:
        return True  # Auth disabled in dev mode
    if not provided:
        return False
    # ПОЧЕМУ secrets.compare_digest: обычное == уязвимо к timing attack —
    # по разнице времени ответа можно угадывать символы ключа по одному.
    return secrets.compare_digest(provided, settings.API_KEY)


async def auth_middleware(request: Request, call_next):
    """Check Authorization: Bearer <key> header on protected endpoints."""
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    # Skip auth if API_KEY is not configured (dev mode)
    if not settings.API_KEY:
        return await call_next(request)

    # Extract token from header
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    if not _verify_key(token):
        logger.warning("auth_failed", path=request.url.path, client=request.client.host if request.client else "unknown")
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or missing API key"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await call_next(request)


def verify_websocket_token(websocket: WebSocket) -> bool:
    """Verify API key for WebSocket connections.

    Checks: 1) Authorization header, 2) ?token= query param.
    ПОЧЕМУ query param как fallback: некоторые WebSocket клиенты
    не поддерживают кастомные headers при handshake.
    """
    if not settings.API_KEY:
        return True  # Auth disabled

    # Check header first
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        if _verify_key(auth_header[7:]):
            return True

    # Fallback: query param
    token = websocket.query_params.get("token")
    return _verify_key(token)
