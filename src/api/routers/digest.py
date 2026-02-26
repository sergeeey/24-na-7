"""Роутер для генерации дайджестов."""
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query, Path as PathParam
from fastapi.responses import Response

from src.utils.config import settings  # noqa: F401
from src.utils.logging import get_logger
from src.digest.generator import DigestGenerator
from src.digest.analyzer import InformationDensityAnalyzer

logger = get_logger("api.digest")
router = APIRouter(prefix="/digest", tags=["digest"])


@router.get("/daily")
def get_digest_daily(
    date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
    user_id: str | None = Query(None, description="Идентификатор пользователя (опционально)"),
):
    """
    Дневной итог в формате для Android: summary_text, key_themes, emotions, actions, total_recordings, total_duration.
    
    **Пример запроса:**
    ```bash
    curl "http://localhost:8000/digest/daily?date=2024-02-17&user_id=user123"
    ```
    """
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    try:
        generator = DigestGenerator()
        return generator.get_daily_digest_json(parsed_date, user_id=user_id)
    except Exception as e:
        logger.exception("digest_daily_failed", date=date, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today")
async def get_digest_today(format: str = Query("markdown", regex="^(markdown|json)$")):
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
        raise HTTPException(status_code=500, detail=f"Failed to generate digest: {str(e)}")


@router.get("/{target_date}")
async def get_digest(
    target_date: str = PathParam(..., description="Дата в формате YYYY-MM-DD"),
    format: str = Query("markdown", regex="^(markdown|json)$"),
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
        raise HTTPException(status_code=500, detail=f"Failed to generate digest: {str(e)}")


@router.get("/{target_date}/density")
async def get_density_analysis(
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
        raise HTTPException(status_code=500, detail=f"Failed to analyze density: {str(e)}")


