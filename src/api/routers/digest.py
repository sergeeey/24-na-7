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
from src.storage.ingest_persist import write_digest_cache
from src.memory.truth import recheck_non_trusted_for_range, reclassify_episodes_for_range

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


def _resolve_review_dates(
    days_back: int,
    date_from: str | None,
    date_to: str | None,
) -> list[date]:
    """Возвращает список дат для review-окна."""
    if date_from or date_to:
        if not (date_from and date_to):
            raise HTTPException(status_code=400, detail="date_from and date_to must be provided together")
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d").date()
            end = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc
        if end < start:
            raise HTTPException(status_code=400, detail="date_to must be greater than or equal to date_from")
    else:
        end = date.today()
        start = end - timedelta(days=max(days_back - 1, 0))
    delta = (end - start).days
    return [start + timedelta(days=offset) for offset in range(delta + 1)]


def _candidate_action(
    *,
    degraded: bool,
    trusted_count: int,
    uncertain_count: int,
    garbage_count: int,
    quarantined_count: int,
    source_unit: str,
) -> str:
    """Консервативно выбирает следующий безопасный шаг для дня."""
    if not degraded and trusted_count > 0:
        return "observe"
    if degraded and trusted_count == 0 and (garbage_count + quarantined_count) > 0:
        return "reclassify"
    if degraded and (uncertain_count + quarantined_count) > 0:
        return "recheck"
    if source_unit == "transcription" and trusted_count > 0:
        return "rebuild_digest"
    return "observe"


def _build_day_review(parsed_date: date, generator: DigestGenerator) -> dict:
    """Строит компактный review summary по одному дню."""
    day_key = parsed_date.isoformat()
    db = get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")

    digest_data = _get_cached_digest(day_key)
    if not digest_data or digest_data.get("_status") == "generating":
        digest_data = generator.get_daily_digest_json(parsed_date)

    trusted_count = int(
        db.fetchone("SELECT COUNT(*) AS c FROM episodes WHERE day_key = ? AND quality_state = 'trusted'", (day_key,))["c"]
    )
    uncertain_count = int(
        db.fetchone("SELECT COUNT(*) AS c FROM episodes WHERE day_key = ? AND quality_state = 'uncertain'", (day_key,))["c"]
    )
    garbage_count = int(
        db.fetchone("SELECT COUNT(*) AS c FROM episodes WHERE day_key = ? AND quality_state = 'garbage'", (day_key,))["c"]
    )
    quarantined_count = int(
        db.fetchone("SELECT COUNT(*) AS c FROM episodes WHERE day_key = ? AND quality_state = 'quarantined'", (day_key,))["c"]
    )
    day_thread_count = int(
        db.fetchone("SELECT COUNT(*) AS c FROM day_threads WHERE day_key = ?", (day_key,))["c"]
    )
    long_thread_count = int(
        db.fetchone(
            """
            SELECT COUNT(DISTINCT long_thread_key) AS c
            FROM day_threads
            WHERE day_key = ? AND COALESCE(long_thread_key, '') != ''
            """,
            (day_key,),
        )["c"]
    )
    episodes_used = int(digest_data.get("episodes_used") or 0)
    degraded = bool(digest_data.get("degraded"))
    source_unit = str(digest_data.get("source_unit") or "transcription")
    incomplete_context = bool(digest_data.get("incomplete_context"))

    return {
        "date": day_key,
        "degraded": degraded,
        "source_unit": source_unit,
        "trusted_count": trusted_count,
        "uncertain_count": uncertain_count,
        "garbage_count": garbage_count,
        "quarantined_count": quarantined_count,
        "day_thread_count": day_thread_count,
        "long_thread_count": long_thread_count,
        "episodes_used": episodes_used,
        "digest_incomplete_context": incomplete_context,
        "candidate_action": _candidate_action(
            degraded=degraded,
            trusted_count=trusted_count,
            uncertain_count=uncertain_count,
            garbage_count=garbage_count,
            quarantined_count=quarantined_count,
            source_unit=source_unit,
        ),
    }


def _preview_summary(preview: dict) -> dict:
    """Сводит dry-run preview к компактной форме для review API."""
    return {
        "affected_days": preview.get("affected_days", []),
        "affected_episodes": len(preview.get("episodes", [])),
        "affected_transcriptions": len(preview.get("transcriptions", [])),
        "proposed_episode_state_counts": preview.get("state_counts", {}),
        "proposed_transcription_state_counts": preview.get("transcription_state_counts", {}),
        "would_write_transitions": int(preview.get("changed_episode_count", 0))
        + int(preview.get("changed_transcription_count", 0)),
        "would_rebuild_digests": len(preview.get("affected_days", [])),
    }


def _build_action_preview(target_date: date) -> dict:
    """Возвращает безопасный preview последствий recheck/reclassify без мутаций."""
    db_path = settings.STORAGE_PATH / "reflexio.db"
    day_key = target_date.isoformat()
    recheck_preview = recheck_non_trusted_for_range(
        db_path,
        start_day=day_key,
        end_day=day_key,
        apply_changes=False,
    )
    reclassify_preview = reclassify_episodes_for_range(
        db_path,
        start_day=day_key,
        end_day=day_key,
        apply_changes=False,
    )
    return {
        "recheck": _preview_summary(recheck_preview),
        "reclassify": _preview_summary(reclassify_preview),
    }


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


@router.get("/review")
@limiter.limit("20/minute")
async def get_digest_review(
    request: Request,
    response: Response,
    days_back: int = Query(7, ge=1, le=365),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    only_degraded: bool = Query(False),
):
    """Возвращает безопасный обзор качества памяти по дням."""
    dates = _resolve_review_dates(days_back, date_from, date_to)
    generator = DigestGenerator()
    review_days = [_build_day_review(target_date, generator) for target_date in reversed(dates)]
    if only_degraded:
        review_days = [item for item in review_days if item["degraded"]]
    return {
        "days_back": days_back,
        "date_from": dates[0].isoformat() if dates else None,
        "date_to": dates[-1].isoformat() if dates else None,
        "only_degraded": only_degraded,
        "days": review_days,
    }


@router.get("/review/{target_date}")
@limiter.limit("30/minute")
async def get_digest_review_day(
    request: Request,
    response: Response,
    target_date: str = PathParam(..., description="Дата в формате YYYY-MM-DD"),
):
    """Возвращает compact review summary по одному дню."""
    try:
        parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc

    generator = DigestGenerator()
    summary = _build_day_review(parsed_date, generator)
    action_preview = _build_action_preview(parsed_date)
    return {
        **summary,
        "recommended_action": summary["candidate_action"],
        "action_preview": action_preview,
        "trusted_episode_present": summary["trusted_count"] > 0,
        "transcript_fallback_only": summary["source_unit"] == "transcription",
    }


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


