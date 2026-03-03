"""Роутер для генерации дайджестов."""
import json as _json
from datetime import date, datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Path as PathParam, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.utils.config import settings  # noqa: F401
from src.utils.logging import get_logger
from src.digest.generator import DigestGenerator
from src.digest.analyzer import InformationDensityAnalyzer
from src.storage.db import get_reflexio_db

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
    except Exception:
        pass
    return None


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
    Дневной итог для Android. Логика:
    1. Есть кеш → мгновенный ответ
    2. Сегодня до 18:30 → предыдущий день + status=pending
    3. force=true или прошедшая дата → генерация inline (может занять 2-5 мин)
    """
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    today = datetime.now().date()
    now = datetime.now()

    # 1. Проверяем кеш (если не force)
    if not force:
        cached = _get_cached_digest(date)
        if cached and "_status" not in cached:
            return cached
        if cached and cached.get("_status") == "generating":
            # Идёт генерация — показываем предыдущий день
            prev_date = (parsed_date - timedelta(days=1)).isoformat()
            prev_cached = _get_cached_digest(prev_date)
            if prev_cached and "_status" not in prev_cached:
                prev_cached["_notice"] = "Анализ за сегодня готовится, показан предыдущий день"
                prev_cached["_target_date"] = date
                prev_cached["_status"] = "generating"
                return prev_cached
            return {
                "date": date,
                "summary_text": "Анализ дня готовится…",
                "key_themes": [],
                "emotions": [],
                "actions": [],
                "total_recordings": 0,
                "total_duration": "0m 0s",
                "repetitions": [],
                "_status": "generating",
                "_notice": "Качественный анализ требует времени. Дайджест будет готов к 18:30.",
            }

    # 2. Сегодня до 18:30 → показываем вчера
    if parsed_date == today and not force:
        is_before_ready = (
            now.hour < _DIGEST_READY_HOUR
            or (now.hour == _DIGEST_READY_HOUR and now.minute < _DIGEST_READY_MINUTE)
        )
        if is_before_ready:
            yesterday = (today - timedelta(days=1)).isoformat()
            prev_cached = _get_cached_digest(yesterday)
            if prev_cached and "_status" not in prev_cached:
                prev_cached["_notice"] = "Сегодняшний дайджест будет готов к 18:30. Показан вчерашний."
                prev_cached["_target_date"] = date
                prev_cached["_status"] = "pending"
                return prev_cached
            # Нет кеша за вчера — генерируем вчера inline и кешируем
            try:
                generator = DigestGenerator()
                yesterday_date = today - timedelta(days=1)
                result = generator.get_daily_digest_json(yesterday_date, user_id=user_id)
                # Кешируем вчера чтобы следующий запрос был мгновенным
                try:
                    db = get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")
                    db.execute(
                        "INSERT OR REPLACE INTO digest_cache (date, digest_json, generated_at, status) VALUES (?, ?, ?, ?)",
                        (yesterday, _json.dumps(result, ensure_ascii=False), datetime.now().isoformat(), "ready"),
                    )
                    db.conn.commit()
                except Exception:
                    pass
                result["_notice"] = "Сегодняшний дайджест будет готов к 18:30. Показан вчерашний."
                result["_target_date"] = date
                result["_status"] = "pending"
                return result
            except Exception:
                return {
                    "date": date,
                    "summary_text": "",
                    "key_themes": [],
                    "emotions": [],
                    "actions": [],
                    "total_recordings": 0,
                    "total_duration": "0m 0s",
                    "repetitions": [],
                    "_status": "pending",
                    "_notice": "Дайджест будет готов к 18:30. Записи за вчера отсутствуют.",
                }

    # 3. Генерация inline (force=true, или прошедшая дата без кеша, или после 18:30)
    try:
        generator = DigestGenerator()
        result = generator.get_daily_digest_json(parsed_date, user_id=user_id)
        # Кешируем результат
        try:
            db = get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")
            db.execute(
                "INSERT OR REPLACE INTO digest_cache (date, digest_json, generated_at, status) VALUES (?, ?, ?, ?)",
                (date, _json.dumps(result, ensure_ascii=False), datetime.now().isoformat(), "ready"),
            )
            db.conn.commit()
        except Exception:
            pass
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


