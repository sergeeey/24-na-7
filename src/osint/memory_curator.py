"""
Memory Curation Agent — курация и обновление Memory Bank.

Пересматривает утверждения, удаляет устаревшие, обновляет достоверность на основе новых данных.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.osint.schemas import ValidatedClaim
from src.osint.deepconf import validate_claims
from src.osint.collector import gather_osint
from src.osint.dq_metrics import calculate_dq_metrics

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.curator")
except Exception:
    import logging
    logger = logging.getLogger("osint.curator")


def load_memory_bank_claims(memory_path: Path = Path(".cursor/memory/osint_research.md")) -> List[Dict[str, Any]]:
    """
    Загружает утверждения из Memory Bank.
    
    Args:
        memory_path: Путь к файлу Memory Bank
        
    Returns:
        Список утверждений с метаданными
    """
    claims = []
    
    if not memory_path.exists():
        logger.warning("memory_bank_not_found", path=str(memory_path))
        return claims
    
    try:
        content = memory_path.read_text(encoding="utf-8")
        
        # Парсим markdown для извлечения утверждений
        # Простая эвристика: ищем строки с ✅/❌/⚠️ и следующий текст
        import re
        
        # Паттерн для поиска утверждений в markdown
        claim_pattern = r'## \d+\.\s*([✅❌⚠️❓])\s*(.+?)(?=\n##|\Z)'
        
        matches = re.finditer(claim_pattern, content, re.DOTALL)
        
        for match in matches:
            status_icon = match.group(1)
            claim_text = match.group(2).strip()
            
            # Извлекаем метаданные (status, confidence и т.д.)
            status_map = {
                "✅": "supported",
                "❌": "refuted",
                "⚠️": "uncertain",
            }
            
            # Пытаемся извлечь confidence из текста
            confidence_match = re.search(r'Confidence.*?(\d+\.\d+)', claim_text)
            confidence = float(confidence_match.group(1)) if confidence_match else 0.5
            
            # Извлекаем источники
            sources_match = re.findall(r'https?://[^\s)]+', claim_text)
            
            claims.append({
                "text": claim_text.split("\n")[0][:200],  # Первая строка
                "status": status_map.get(status_icon, "uncertain"),
                "confidence": confidence,
                "sources": sources_match[:3],
                "raw_text": claim_text,
            })
        
        logger.info("memory_bank_claims_loaded", count=len(claims))
        
    except Exception as e:
        logger.error("memory_bank_load_failed", error=str(e))
    
    return claims


def check_claim_age(claim_date_str: Optional[str], max_age_days: int = 30) -> bool:
    """
    Проверяет возраст утверждения.
    
    Args:
        claim_date_str: Дата утверждения в ISO формате
        max_age_days: Максимальный возраст в днях
        
    Returns:
        True если утверждение устарело
    """
    if not claim_date_str:
        return True  # Если даты нет, считаем устаревшим
    
    try:
        claim_date = datetime.fromisoformat(claim_date_str.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - claim_date).days
        return age > max_age_days
    except Exception:
        return True


def should_revalidate_claim(claim: Dict[str, Any], threshold: float = 0.8) -> bool:
    """
    Определяет, нужно ли ревалидировать утверждение.
    
    Args:
        claim: Утверждение
        threshold: Порог уверенности для ревалидации
        
    Returns:
        True если нужно ревалидировать
    """
    confidence = claim.get("confidence", 0.5)
    status = claim.get("status", "uncertain")
    
    # Ревалидируем если:
    # 1. Confidence ниже порога
    # 2. Статус uncertain
    # 3. Утверждение устарело (проверяется отдельно)
    
    return confidence < threshold or status == "uncertain"


def revalidate_claim(claim: Dict[str, Any]) -> Optional[ValidatedClaim]:
    """
    Ревалидирует утверждение на основе новых источников.
    
    Args:
        claim: Утверждение для ревалидации
        
    Returns:
        Ревалидированное утверждение или None
    """
    try:
        claim_text = claim.get("text", "")
        
        if not claim_text:
            return None
        
        # Выполняем новый поиск
        sources = gather_osint(claim_text, limit=5, scrape_content=True)
        
        if not sources:
            logger.warning("revalidation_no_sources", claim=claim_text[:50])
            return None
        
        # Валидируем заново
        from src.osint.schemas import Claim
        from datetime import datetime, timezone
        
        new_claim = Claim(
            text=claim_text,
            source_urls=[s.url for s in sources],
            confidence=claim.get("confidence", 0.5),
            category=None,
            extracted_at=datetime.now(timezone.utc).isoformat(),
        )
        
        validated = validate_claims([new_claim], sources)
        
        if validated:
            return validated[0]
        
        return None
        
    except Exception as e:
        logger.error("revalidation_failed", claim=claim.get("text", "")[:50], error=str(e))
        return None


def curate_memory_bank(
    memory_path: Path = Path(".cursor/memory/osint_research.md"),
    max_age_days: int = 30,
    confidence_threshold: float = 0.8,
    remove_refuted: bool = True,
) -> Dict[str, Any]:
    """
    Выполняет курацию Memory Bank с DQ метриками.
    
    Args:
        memory_path: Путь к Memory Bank
        max_age_days: Максимальный возраст утверждений
        confidence_threshold: Порог уверенности для ревалидации
        remove_refuted: Удалять ли опровергнутые утверждения
        
    Returns:
        Статистика курации с DQ метриками
    """
    stats = {
        "total_claims": 0,
        "refuted_removed": 0,
        "outdated_removed": 0,
        "revalidated": 0,
        "kept": 0,
        "dq_metrics": {},
    }
    
    logger.info("memory_curation_started", threshold=confidence_threshold)
    
    # Загружаем утверждения
    claims = load_memory_bank_claims(memory_path)
    stats["total_claims"] = len(claims)
    
    curated_claims = []
    
    for claim in claims:
        status = claim.get("status", "uncertain")
        _ = claim.get("confidence", 0.5)  # резерв для фильтрации по порогу
        
        # Удаляем опровергнутые если нужно
        if remove_refuted and status == "refuted":
            stats["refuted_removed"] += 1
            logger.debug("claim_removed_refuted", claim=claim.get("text", "")[:50])
            continue
        
        # Проверяем возраст (упрощённо - проверяем по дате файла)
        # В реальности нужно хранить даты в структурированном формате
        file_age = (datetime.now(timezone.utc) - datetime.fromtimestamp(memory_path.stat().st_mtime, tz=timezone.utc)).days
        
        if file_age > max_age_days:
            # Ревалидируем устаревшие
            if should_revalidate_claim(claim, confidence_threshold):
                logger.info("revalidating_claim", claim=claim.get("text", "")[:50])
                
                revalidated = revalidate_claim(claim)
                
                if revalidated:
                    # Обновляем утверждение
                    claim["status"] = revalidated.validation_status
                    claim["confidence"] = revalidated.calibrated_confidence
                    claim["sources"] = revalidated.evidence
                    stats["revalidated"] += 1
                else:
                    stats["outdated_removed"] += 1
                    continue
        
        # Сохраняем утверждение
        curated_claims.append(claim)
        stats["kept"] += 1
    
    # Вычисляем DQ метрики
    if curated_claims:
        dq_metrics = calculate_dq_metrics(curated_claims, max_age_days)
        stats["dq_metrics"] = dq_metrics
        
        logger.info(
            "dq_metrics_calculated",
            accuracy=dq_metrics["accuracy"],
            completeness=dq_metrics["completeness"],
            timeliness=dq_metrics["timeliness"],
            consistency=dq_metrics["consistency"],
            validity=dq_metrics["validity"],
            overall_dq=dq_metrics["overall_dq_score"],
        )
        
        # TODO: Реализовать сохранение обновлённых утверждений
        logger.info("memory_curation_completed", stats=stats)
    else:
        # Если нет утверждений, устанавливаем нулевые метрики
        stats["dq_metrics"] = {
            "accuracy": 0.0,
            "completeness": 0.0,
            "timeliness": 0.0,
            "consistency": 1.0,
            "validity": 0.0,
            "overall_dq_score": 0.0,
        }
    
    return stats


def main():
    """CLI для курации Memory Bank."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Memory Curation Agent")
    parser.add_argument(
        "--max-age",
        type=int,
        default=30,
        help="Максимальный возраст утверждений в днях",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Порог уверенности для ревалидации",
    )
    parser.add_argument(
        "--remove-refuted",
        action="store_true",
        help="Удалять опровергнутые утверждения",
    )
    
    args = parser.parse_args()
    
    stats = curate_memory_bank(
        max_age_days=args.max_age,
        confidence_threshold=args.threshold,
        remove_refuted=args.remove_refuted,
    )
    
    print("\n" + "=" * 70)
    print("Memory Bank Curation Complete")
    print("=" * 70)
    print(f"Total claims: {stats['total_claims']}")
    print(f"Refuted removed: {stats['refuted_removed']}")
    print(f"Outdated removed: {stats['outdated_removed']}")
    print(f"Revalidated: {stats['revalidated']}")
    print(f"Kept: {stats['kept']}")
    print("=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

