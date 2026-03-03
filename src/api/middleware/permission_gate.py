"""
Permission Gate — подтверждение необратимых WRITE операций.

ПОЧЕМУ нужен:
  IRREVERSIBLE операции (удалить данные, принудительно перегенерировать дайджест)
  не должны выполняться немедленно. Пользователь должен сначала получить
  confirmation_token, потом подтвердить его в течение 60 сек.

Схема:
  1. POST /query/digest_generation → 403 {requires_confirmation: true, token: "abc123", expires_in: 60}
  2. POST /query/digest_generation?confirm_token=abc123 → выполняется

Хранение токенов: in-memory (Redis если RATE_LIMIT_STORAGE=redis).
Токен живёт 60 сек, одноразовый.

Audit log: каждый WRITE-запрос логируется в write_audit таблицу.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Optional

from src.utils.logging import get_logger

logger = get_logger("api.permission_gate")

_TOKEN_TTL = 60  # секунды
_STORE: dict[str, dict] = {}  # in-memory fallback


def _redis_client():
    """Получить Redis если доступен."""
    try:
        import redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        return redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
    except Exception:
        return None


def issue_confirmation_token(operation: str, payload: dict) -> dict:
    """
    Выдать confirmation token для IRREVERSIBLE операции.

    Returns:
      {requires_confirmation: True, token: str, expires_in: 60, operation: str}
    """
    token = _make_token(operation, payload)
    entry = {
        "operation": operation,
        "payload": payload,
        "issued_at": time.time(),
        "ttl": _TOKEN_TTL,
    }

    r = _redis_client()
    if r:
        try:
            r.setex(f"pgate:{token}", _TOKEN_TTL, json.dumps(entry))
        except Exception:
            _STORE[token] = entry
    else:
        _STORE[token] = entry

    logger.info(
        "confirmation_token_issued",
        operation=operation,
        token=token[:8] + "...",
    )
    return {
        "requires_confirmation": True,
        "token": token,
        "expires_in": _TOKEN_TTL,
        "operation": operation,
        "message": f"Send the same request with ?confirm_token={token} within {_TOKEN_TTL}s to proceed.",
    }


def verify_and_consume_token(token: str, operation: str) -> Optional[dict]:
    """
    Проверить и удалить токен. Returns payload если валиден, None если нет.
    """
    r = _redis_client()
    key = f"pgate:{token}"
    entry_raw = None

    if r:
        try:
            entry_raw = r.get(key)
            if entry_raw:
                r.delete(key)
        except Exception:
            pass

    if entry_raw is None:
        entry_raw_dict = _STORE.pop(token, None)
        if entry_raw_dict:
            entry_raw = json.dumps(entry_raw_dict)

    if not entry_raw:
        logger.warning("confirmation_token_not_found", token=token[:8] + "...")
        return None

    entry = json.loads(entry_raw) if isinstance(entry_raw, str) else entry_raw

    # Проверяем TTL (для in-memory fallback)
    if time.time() - entry.get("issued_at", 0) > _TOKEN_TTL:
        logger.warning("confirmation_token_expired", token=token[:8] + "...")
        return None

    if entry.get("operation") != operation:
        logger.warning(
            "confirmation_token_wrong_operation",
            expected=operation,
            got=entry.get("operation"),
        )
        return None

    logger.info("confirmation_token_consumed", operation=operation)
    return entry.get("payload", {})


def log_write_operation(operation: str, payload: dict, result: str) -> None:
    """Аудит лог WRITE операции в structured log."""
    logger.info(
        "write_operation",
        operation=operation,
        payload_keys=list(payload.keys()),
        result=result,
    )
    # Пишем в БД если доступна
    try:
        from src.storage.db import get_reflexio_db
        db = get_reflexio_db()
        db.execute(
            """
            INSERT INTO event_log (session_id, stage, status, details, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (
                str(uuid.uuid4()),
                f"WRITE:{operation}",
                result,
                json.dumps({"payload_keys": list(payload.keys())}),
            ),
        )
        db.conn.commit()
    except Exception as e:
        logger.warning("write_audit_db_failed", error=str(e))


def _make_token(operation: str, payload: dict) -> str:
    raw = f"{operation}:{json.dumps(payload, sort_keys=True)}:{uuid.uuid4()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
