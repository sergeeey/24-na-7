"""Роутер для генерации дайджестов."""
import json as _json
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query, Path as PathParam, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.utils.config import settings  # noqa: F401
from src.utils.logging import get_logger
from src.digest.generator import DigestGenerator
from src.digest.analyzer import InformationDensityAnalyzer
from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import write_digest_cache

logger = get_logger("api.digest")
router = APIRouter(prefix="/digest", tags=["digest"])
limiter = Limiter(key_func=get_remote_address)

# ПОЧЕМУ UTC: VPS и Docker контейнер в UTC. Алматы = UTC+6.
# 18:30 Алматы = 12:30 UTC. Все сравнения datetime.now() в UTC.
_DIGEST_READY_HOUR = 12   # 12:00 UTC = 18:00 Алматы
_DIGEST_READY_MINUTE = 30  # 12:30 UTC = 18:30 Алматы


def _get_cached_digest(target_date: str) -> dict | None:
    """Проверяет кеш дайджестов. Возвращает dict или None."""
    try:
        db = get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")
        row = db.fetchone(
            "SELECT digest_json, status FROM digest_cache WHERE date = ?",
            (target_date,),
        )
        if row and row["status"] == "ready":
            return _json.loads(row["digest_json"])
        if row and row["status"] == "generating":
            return {"_status": "generating"}
    except Exception as e:
        logger.debug("digest_cache_read_failed", date=target_date, error=str(e))
    return None


def _is_effectively_empty_digest(result: dict, parsed_date: date) -> bool:
    """Определяет, есть ли у дайджеста достаточно trusted-контекста для обычного ответа."""
    total_recordings = int(result.get("total_recordings") or 0)
    episodes_used = int(result.get("episodes_used") or 0)
    source_unit = result.get("source_unit") or "transcription"
    degraded = bool(result.get("degraded"))
    evidence_strength = float(result.get("evidence_strength") or 0.0)
    summary_text = (result.get("summary_text") or "").strip()
    if total_recordings <= 0:
        return True
    if source_unit == "episode" and episodes_used <= 0:
        return True
    if degraded and source_unit == "transcription" and evidence_strength <= 0.0:
        return True
    if summary_text.startswith("Нет записей за день"):
        return True
    return False


@router.get("/daily")
@limiter.limit("30/minute")
async def get_digest_daily(
    request: Request,
    response: Response,
    date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
    user_id: str | None = Query(None, description="Идентификатор пользователя (опционально)"),
    force: bool = Query(False, description="Принудительная генерация (без кеша)"),
):
    """
    Дневной итог для Android. Единый источник с GET /query/digest:
    1. Есть кеш за дату → мгновенный ответ
    2. Нет кеша → генерация на лету за запрошенную дату (как query.get_digest)
    3. Пусто → один формат _status=empty, _notice для UI
    """
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # 1. Кеш за запрошенную дату (если не force)
    if not force:
        cached = _get_cached_digest(date)
        if cached and cached.get("_status") != "generating":
            return cached
        # status=generating → всё равно отдаём live за дату ниже

    # 2. Генерация на лету за запрошенную дату (согласовано с query.get_digest)
    try:
        generator = DigestGenerator()
        result = generator.get_daily_digest_json(parsed_date, user_id=user_id)
        if _is_effectively_empty_digest(result, parsed_date):
            today = datetime.now().date()
            notice = (
                "Пока нет записей за сегодня."
                if parsed_date == today
                else "Нет записей за этот день."
            )
            return {
                "date": date,
                "summary_text": "",
                "key_themes": [],
                "emotions": [],
                "actions": [],
                "total_recordings": 0,
                "total_duration": "0m 0s",
                "repetitions": [],
                "_status": "empty",
                "_notice": notice,
            }
        result["_lineage"] = result.get("_lineage") or {}
        result["_lineage"]["live"] = True
        # Кешируем для следующих запросов
        try:
            db = get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")
            previous = db.fetchone(
                "SELECT generated_at FROM digest_cache WHERE date = ?",
                (date,),
            )
            write_digest_cache(
                settings.STORAGE_PATH / "reflexio.db",
                day_key=date,
                digest_json=_json.dumps(result, ensure_ascii=False),
                status="ready",
                previous_digest_id=(
                    f"digest:{date}:{previous['generated_at']}" if previous and previous["generated_at"] else None
                ),
                rebuild_reason="digest_daily_force" if force else "digest_daily_live",
                rebuilt_at=datetime.now().isoformat(),
                changed_source_count=int(result.get("total_recordings") or 0),
            )
        except Exception as e:
            logger.warning("digest_cache_write_failed", date=date, error=str(e))
        return result
    except Exception as e:
        logger.exception("digest_daily_failed", date=date, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate digest. Check server logs.")


@router.get("/today")
@limiter.limit("20/minute")
async def get_digest_today(request: Request, response: Response, format: str = Query("markdown", pattern="^(markdown|json)$")):
    """
    Получает дайджест за сегодня.
    
    Args:
        format: Формат ответа (markdown или json)
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/digest/today?format=json"
    ```
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
            content = output_file.read_text(encoding="utf-8")
            return Response(content=content, media_type="text/markdown")
            
    except Exception as e:
        logger.error("digest_generation_failed", date="today", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate digest. Check server logs.")


@router.get("/{target_date}")
@limiter.limit("20/minute")
async def get_digest(
    request: Request,
    response: Response,
    target_date: str = PathParam(..., description="Дата в формате YYYY-MM-DD"),
    format: str = Query("markdown", pattern="^(markdown|json)$"),
):
    """
    Получает дайджест за указанную дату.
    
    Args:
        target_date: Дата в формате YYYY-MM-DD
        format: Формат ответа (markdown или json)
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/digest/2024-02-17?format=json"
    ```
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
            content = output_file.read_text(encoding="utf-8")
            return Response(content=content, media_type="text/markdown")
            
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        logger.error("digest_generation_failed", date=target_date, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate digest. Check server logs.")


@router.get("/{target_date}/sources")
@limiter.limit("60/minute")
async def get_digest_sources_endpoint(
    request: Request,
    response: Response,
    target_date: str = PathParam(..., description="Дата в формате YYYY-MM-DD"),
):
    """
    Data lineage дайджеста — какие транскрипции вошли в итог за день.

    Отвечает на вопрос: "откуда этот инсайт?" → клик на инсайт → список оригинальных записей.
    Также используется для GDPR cascading delete: при удалении данных пользователя
    можно найти все дайджесты, которые их использовали.

    GET /digest/2026-03-03/sources
    """
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    from src.storage.digest_lineage import get_digest_sources
    return get_digest_sources(target_date)


@router.get("/{target_date}/density")
@limiter.limit("10/minute")
async def get_density_analysis(
    request: Request,
    response: Response,
    target_date: str = PathParam(..., description="Дата в формате YYYY-MM-DD"),
):
    """
    Получает анализ информационной плотности за указанную дату.
    
    Args:
        target_date: Дата в формате YYYY-MM-DD
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/digest/2024-02-17/density"
    ```
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
        raise HTTPException(status_code=500, detail="Failed to analyze density. Check server logs.")


