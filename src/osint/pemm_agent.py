"""
PEMM Agent — стратегический агент для управления OSINT миссиями.

Реализует декомпозицию миссий, управление задачами и координацию компонентов KDS.
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.osint.collector import gather_osint
from src.osint.contextor import build_rctf_prompt, extract_claims_from_response, create_default_claim_schema
from src.osint.deepconf import validate_claims
from src.osint.schemas import Mission, MissionResult, Claim, ValidatedClaim
from src.osint.zone_manager import get_zone_for_mission

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.pemm")
except Exception:
    import logging
    logger = logging.getLogger("osint.pemm")


def call_llm_actor(prompt: str, model: Optional[str] = None) -> str:
    """
    Вызывает LLM-актора для генерации утверждений из промпта.
    
    Args:
        prompt: R.C.T.F. промпт
        model: Имя модели (опционально, для будущей поддержки разных моделей)
        
    Returns:
        Ответ от LLM
    """
    # TODO: Интеграция с реальной LLM API
    # Пока возвращаем заглушку
    
    logger.debug("llm_actor_called", prompt_length=len(prompt))
    
    # Заглушка для демонстрации
    # В реальности здесь должен быть вызов OpenAI, Anthropic, или локальной модели
    return json.dumps({
        "claims": [
            {
                "text": "Example claim extracted from sources",
                "category": "information",
                "confidence": 0.7,
            }
        ]
    })


def save_to_memory(validated_claims: List[ValidatedClaim], mission_id: str) -> bool:
    """
    Сохраняет валидированные утверждения в Memory Bank (файл + Supabase).
    
    Args:
        validated_claims: Список валидированных утверждений
        mission_id: ID миссии
        
    Returns:
        True если успешно сохранено
    """
    success = True
    
    # 1. Сохранение в файл (для обратной совместимости)
    try:
        memory_path = Path(".cursor/memory/osint_research.md")
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        
        lines = [
            f"# OSINT Research: Mission {mission_id}",
            "",
            f"**Date:** {datetime.now(timezone.utc).isoformat()}",
            f"**Validated Claims:** {len(validated_claims)}",
            "",
            "---",
            "",
        ]
        
        for idx, vclaim in enumerate(validated_claims, 1):
            claim = vclaim.claim
            status_icon = {
                "supported": "✅",
                "refuted": "❌",
                "uncertain": "⚠️",
            }.get(vclaim.validation_status, "❓")
            
            lines.append(f"## {idx}. {status_icon} {claim.text[:100]}...")
            lines.append(f"**Status:** {vclaim.validation_status}")
            lines.append(f"**Confidence:** {vclaim.calibrated_confidence:.2f}")
            lines.append(f"**Sources:** {', '.join(claim.source_urls[:3])}")
            if vclaim.evidence:
                lines.append(f"**Evidence:** {', '.join(vclaim.evidence[:3])}")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # Добавляем в файл (append mode)
        with memory_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        logger.info("memory_file_saved", mission_id=mission_id, claims_count=len(validated_claims))
        
    except Exception as e:
        logger.error("memory_file_save_failed", mission_id=mission_id, error=str(e))
        success = False
    
    # 2. Сохранение в Supabase (если настроено)
    try:
        from src.storage.db import get_db
        import uuid
        
        db = get_db()
        
        # Сохраняем миссию
        mission_data = {
            "id": mission_id,
            "name": mission_id,
            "status": "completed",
            "parameters": {},
        }
        
        try:
            db.insert("missions", mission_data)
        except Exception:
            # Миссия уже существует, обновляем
            try:
                db.update("missions", mission_id, {"status": "completed"})
            except Exception:
                pass
        
        # Сохраняем утверждения
        for vclaim in validated_claims:
            claim = vclaim.claim
            
            claim_data = {
                "id": str(uuid.uuid4()),
                "source_url": claim.source_urls[0] if claim.source_urls else None,
                "claim_text": claim.text,
                "confidence": float(vclaim.calibrated_confidence),
                "validated": vclaim.validation_status == "supported",
            }
            
            try:
                db.insert("claims", claim_data)
            except Exception as e:
                logger.warning("claim_insert_failed", claim_id=claim_data["id"], error=str(e))
        
        logger.info("memory_db_saved", mission_id=mission_id, claims_count=len(validated_claims))
        
    except Exception as e:
        logger.debug("memory_db_save_skipped", mission_id=mission_id, error=str(e))
        # Не критично, если БД не настроена
    
    return success


def run_osint_mission(mission: Mission) -> MissionResult:
    """
    Выполняет OSINT миссию используя PEMM методологию.
    
    Args:
        mission: Объект миссии
        
    Returns:
        Результат выполнения миссии
    """
    logger.info("osint_mission_started", mission_id=mission.id, tasks_count=len(mission.tasks))
    
    all_validated_claims = []
    errors = []
    tasks_completed = 0
    
    for task in mission.tasks:
        try:
            logger.info("osint_task_started", task_id=task.id, query=task.query)
            
            # Шаг 1: Сбор данных (Collector)
            # Определяем тип миссии и выбираем зону
            mission_type = "serp" if task.goggle_url or not task.goggle_url else "general"
            zone = get_zone_for_mission(mission_type)
            
            # Используем SERP API если есть API key, иначе Brave Search
            use_serp = os.getenv("BRIGHTDATA_API_KEY") is not None
            
            sources = gather_osint(
                query=task.query,
                goggle_url=task.goggle_url,
                limit=task.max_results,
                scrape_content=True,
                use_serp=use_serp,
                search_engine="google",
                zone=zone,
            )
            
            if not sources:
                logger.warning("osint_task_no_sources", task_id=task.id)
                errors.append(f"Task {task.id}: No sources collected")
                continue
            
            # Шаг 2: Построение R.C.T.F. промпта (Contextor)
            format_schema = task.format_schema or create_default_claim_schema()
            
            context_data = {
                "query": task.query,
                "sources_count": len(sources),
                "task_id": task.id,
            }
            
            prompt = build_rctf_prompt(
                role=task.role,
                context_data=context_data,
                task=task.instruction,
                format_schema=format_schema,
                sources=sources,
            )
            
            # Шаг 3: Генерация утверждений (Actor)
            llm_response = call_llm_actor(prompt)
            
            # Шаг 4: Извлечение утверждений
            raw_claims = extract_claims_from_response(llm_response, format_schema)
            
            # Преобразуем в объекты Claim
            claims = []
            for raw_claim in raw_claims:
                claim_text = raw_claim.get("text", "") if isinstance(raw_claim, dict) else str(raw_claim)
                
                if not claim_text:
                    continue
                
                source_urls = [src.url for src in sources[:3]]  # Связываем с первыми источниками
                
                claims.append(Claim(
                    text=claim_text,
                    source_urls=source_urls,
                    confidence=raw_claim.get("confidence", 0.5) if isinstance(raw_claim, dict) else 0.5,
                    category=raw_claim.get("category") if isinstance(raw_claim, dict) else None,
                    extracted_at=datetime.now(timezone.utc).isoformat(),
                ))
            
            # Шаг 5: Валидация утверждений (DeepConf)
            validated = validate_claims(claims, sources)
            
            all_validated_claims.extend(validated)
            tasks_completed += 1
            
            logger.info(
                "osint_task_completed",
                task_id=task.id,
                claims_count=len(validated),
            )
            
        except Exception as e:
            logger.error("osint_task_failed", task_id=task.id, error=str(e))
            errors.append(f"Task {task.id}: {str(e)}")
    
    # Вычисляем среднюю уверенность
    avg_confidence = 0.0
    if all_validated_claims:
        avg_confidence = sum(vc.calibrated_confidence for vc in all_validated_claims) / len(all_validated_claims)
    
    # Сохраняем в Memory Bank
    save_to_memory(all_validated_claims, mission.id)
    
    result = MissionResult(
        mission_id=mission.id,
        completed_at=datetime.now(timezone.utc).isoformat(),
        tasks_completed=tasks_completed,
        total_claims=len(all_validated_claims),
        validated_claims=len([vc for vc in all_validated_claims if vc.validation_status == "supported"]),
        avg_confidence=avg_confidence,
        claims=all_validated_claims,
        errors=errors,
    )
    
    logger.info(
        "osint_mission_completed",
        mission_id=mission.id,
        tasks_completed=tasks_completed,
        claims_count=len(all_validated_claims),
        avg_confidence=avg_confidence,
    )
    
    return result


def load_mission(mission_path: Path) -> Mission:
    """
    Загружает миссию из JSON файла.
    
    Args:
        mission_path: Путь к JSON файлу миссии
        
    Returns:
        Объект миссии
    """
    try:
        with open(mission_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return Mission(**data)
        
    except Exception as e:
        logger.error("mission_load_failed", path=str(mission_path), error=str(e))
        raise


def main():
    """CLI для запуска OSINT миссий."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PEMM Agent - OSINT Mission Runner")
    parser.add_argument(
        "--mission",
        type=Path,
        required=True,
        help="Path to mission JSON file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file for results",
    )
    
    args = parser.parse_args()
    
    # Загружаем миссию
    mission = load_mission(args.mission)
    
    # Выполняем миссию
    result = run_osint_mission(mission)
    
    # Сохраняем результаты
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
        
        print(f"✅ Mission completed: {args.output}")
    else:
        # Выводим в stdout
        print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    
    print(f"\nMission: {mission.name}")
    print(f"Tasks completed: {result.tasks_completed}/{len(mission.tasks)}")
    print(f"Validated claims: {result.validated_claims}/{result.total_claims}")
    print(f"Average confidence: {result.avg_confidence:.2f}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

