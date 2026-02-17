"""
Health Monitor — периодическая проверка здоровья системы.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("monitor.health")
except Exception:
    import logging
    logger = logging.getLogger("monitor.health")


async def check_health() -> Dict[str, Any]:
    """
    Проверяет здоровье системы.
    
    Returns:
        Результаты проверки
    """
    result = {
        "timestamp": datetime.now().isoformat(),
        "status": "unknown",
        "checks": {},
    }
    
    # Проверка 1: API доступен
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/health")
            result["checks"]["api"] = {
                "status": "ok" if response.status_code == 200 else "fail",
                "status_code": response.status_code,
            }
    except Exception as e:
        result["checks"]["api"] = {
            "status": "fail",
            "error": str(e),
        }
    
    # Проверка 2: База данных
    try:
        from src.storage.db import get_db
        db = get_db()
        
        # Пробуем простой запрос
        db.select("metrics", limit=1)
        result["checks"]["database"] = {
            "status": "ok",
            "backend": type(db).__name__,
        }
    except Exception as e:
        result["checks"]["database"] = {
            "status": "fail",
            "error": str(e),
        }
    
    # Проверка 3: MCP сервисы (опционально)
    try:
        import json
        
        mcp_file = Path(".cursor/mcp.json")
        if mcp_file.exists():
            mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
            mcp_servers = mcp_data.get("mcpServers", {})
            
            # Пытаемся загрузить mcp_validator
            ping_service = None
            try:
                from pathlib import Path as PathLib
                mcp_validator_path = PathLib(__file__).parent.parent.parent / ".cursor" / "validation" / "mcp_validator.py"
                if mcp_validator_path.exists():
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("mcp_validator", mcp_validator_path)
                    mcp_validator = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mcp_validator)
                    ping_service = getattr(mcp_validator, "ping_service", None)
            except Exception:
                pass
            
            mcp_status = {}
            if ping_service:
                for name, config in list(mcp_servers.items())[:3]:  # Проверяем первые 3
                    if config.get("enabled"):
                        try:
                            ping_result = ping_service(name, config)
                            mcp_status[name] = ping_result.get("status", "unknown")
                        except Exception:
                            mcp_status[name] = "unknown"
            
            result["checks"]["mcp"] = {
                "status": "ok" if (ping_service and all(s == "ok" for s in mcp_status.values())) else "warn",
                "services": mcp_status if mcp_status else {"note": "validator not available"},
            }
        else:
            result["checks"]["mcp"] = {
                "status": "warn",
                "error": "mcp.json not found",
            }
    except Exception as e:
        result["checks"]["mcp"] = {
            "status": "warn",
            "error": str(e),
        }
    
    # Определяем общий статус
    all_ok = all(
        check.get("status") == "ok"
        for check in result["checks"].values()
    )
    
    result["status"] = "healthy" if all_ok else "degraded"
    
    return result


async def periodic_check(interval: int = 300):
    """
    Периодическая проверка здоровья системы.
    
    Args:
        interval: Интервал проверки в секундах (по умолчанию 5 минут)
    """
    logger.info("health_monitor_started", interval_seconds=interval)
    
    while True:
        try:
            health_result = await check_health()
            
            status = health_result["status"]
            logger.info(
                "health_check_completed",
                status=status,
                checks_count=len(health_result["checks"]),
            )
            
            # Если система деградировала, логируем предупреждение
            if status == "degraded":
                logger.warning("system_degraded", checks=health_result["checks"])
            
            # Сохраняем результат в метрики (опционально)
            try:
                from src.storage.db import get_db
                db = get_db()
                
                metric_data = {
                    "metric_name": "health_status",
                    "metric_value": 1.0 if status == "healthy" else 0.5,
                    "updated_at": datetime.now().isoformat(),
                }
                
                # Обновляем или вставляем метрику
                existing = db.select("metrics", filters={"metric_name": "health_status"}, limit=1)
                if existing:
                    db.update("metrics", existing[0]["id"], metric_data)
                else:
                    db.insert("metrics", metric_data)
            except Exception as e:
                logger.debug("failed_to_save_health_metric", error=str(e))
            
        except Exception as e:
            logger.error("health_check_failed", error=str(e))
        
        await asyncio.sleep(interval)

