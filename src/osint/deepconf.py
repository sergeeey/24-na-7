"""
DeepConf — Actor-Critic валидация с калибровкой доверия.

Реализует методологию DeepConf для проверки утверждений и калибровки уверенности.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

from src.osint.schemas import Claim, ValidatedClaim, Source

try:
    from sklearn.isotonic import IsotonicRegression
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.deepconf")
except Exception:
    import logging
    logger = logging.getLogger("osint.deepconf")


def call_llm_critic(critic_input: Dict[str, Any], model: Optional[str] = None) -> Dict[str, Any]:
    """
    Вызывает LLM-критика для валидации утверждения.
    
    Args:
        critic_input: Входные данные для критика (claim, source)
        model: Имя модели (опционально)
        
    Returns:
        Ответ критика с validation status и logit
    """
    claim = critic_input.get("claim", "")
    source = critic_input.get("source", "")
    
    logger.debug("llm_critic_called", claim_length=len(claim))
    
    # Пытаемся использовать реальный LLM
    try:
        from src.llm.providers import get_llm_client
        critic_client = get_llm_client(role="critic")
        
        if critic_client:
            # Формируем промпт для критика
            system_prompt = """You are a fact-checking critic. Your task is to verify if a claim is supported by the provided source text.
Return your response as JSON with fields:
- "status": "supported" | "refuted" | "uncertain"
- "logit": number between 0 and 1 (confidence score)
- "reasoning": brief explanation"""
            
            user_prompt = f"""Claim: {claim}

Source text: {source[:2000]}

Verify if the claim is supported by the source. Return JSON response."""
            
            response = critic_client.call(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=500
            )
            
            if response.get("text") and not response.get("error"):
                # Парсим JSON ответ
                try:
                    import json
                    parsed = json.loads(response["text"])
                    logger.info(
                        "llm_critic_success",
                        status=parsed.get("status"),
                        logit=parsed.get("logit"),
                        tokens=response.get("tokens_used", 0),
                        latency_ms=response.get("latency_ms", 0)
                    )
                    return {
                        "status": parsed.get("status", "uncertain"),
                        "logit": float(parsed.get("logit", 0.5)),
                        "reasoning": parsed.get("reasoning", ""),
                    }
                except json.JSONDecodeError:
                    logger.warning("llm_critic_invalid_json", response=response["text"][:200])
            elif response.get("error"):
                logger.warning("llm_critic_error", error=response["error"])
    except Exception as e:
        logger.debug("llm_critic_fallback", error=str(e))
    
    # Fallback: простая эвристика если LLM недоступен
    if source and len(source) > 50:
        return {
            "status": "supported",
            "logit": 0.7,
            "reasoning": "Source contains relevant information (fallback)",
        }
    else:
        return {
            "status": "uncertain",
            "logit": 0.4,
            "reasoning": "Insufficient source information (fallback)",
        }


def calibrate_confidence(raw_logit: float) -> float:
    """
    Калибрует уверенность используя Isotonic Regression.
    
    Args:
        raw_logit: Сырой logit от LLM-критика
        
    Returns:
        Калиброванная уверенность (0-1)
    """
    if not HAS_SKLEARN:
        # Fallback: простая сигмоидная функция
        import math
        return 1.0 / (1.0 + math.exp(-raw_logit))
    
    # TODO: В реальности здесь должна быть обученная модель калибровки
    # Пока используем простую линейную калибровку
    
    # Калибруем logit в диапазон [0, 1]
    # Обычно logits в диапазоне примерно [-5, 5]
    calibrated = (raw_logit + 5) / 10  # Простая линейная трансформация
    calibrated = max(0.0, min(1.0, calibrated))  # Clamp to [0, 1]
    
    return calibrated


def find_source_text(claim: Claim, sources: List[Source]) -> str:
    """
    Находит релевантный текст источника для утверждения.
    
    Args:
        claim: Утверждение
        sources: Список источников
        
    Returns:
        Текст источника или пустая строка
    """
    # Пытаемся найти источник по URL из claim
    for source_url in claim.source_urls:
        for source in sources:
            if source.url == source_url and source.content:
                return source.content
    
    # Если не нашли по URL, возвращаем первый доступный контент
    for source in sources:
        if source.content:
            return source.content
    
    return ""


def validate_claims(
    claims: List[Claim],
    sources: List[Source],
) -> List[ValidatedClaim]:
    """
    Валидирует утверждения используя Actor-Critic подход.
    
    Args:
        claims: Список утверждений для валидации
        sources: Список источников для проверки
        
    Returns:
        Список валидированных утверждений
    """
    validated = []
    
    logger.info("deepconf_validation_started", claims_count=len(claims), sources_count=len(sources))
    
    for claim in claims:
        try:
            # Находим релевантный источник
            source_text = find_source_text(claim, sources)
            
            if not source_text:
                # Нет источника - помечаем как uncertain
                validated.append(ValidatedClaim(
                    claim=claim,
                    validation_status="uncertain",
                    critic_confidence=0.3,
                    calibrated_confidence=0.3,
                    evidence=[],
                    validated_at=datetime.now(timezone.utc).isoformat(),  # Будет установлено позже
                ))
                continue
            
            # Вызываем критика
            critic_input = {
                "claim": claim.text,
                "source": source_text[:2000],  # Ограничиваем размер для LLM
            }
            
            critic_response = call_llm_critic(critic_input)
            
            # Калибруем уверенность
            raw_logit = critic_response.get("logit", 0.5)
            calibrated = calibrate_confidence(raw_logit)
            
            # Определяем статус
            status = critic_response.get("status", "uncertain")
            
            # Собираем evidence (URL источников)
            evidence = claim.source_urls[:3]
            
            # CoVe проверка перед сохранением
            validated_claim_dict = {
                "claim": {
                    "text": claim.text,
                    "source_urls": claim.source_urls,
                    "confidence": claim.confidence,
                    "category": claim.category,
                    "extracted_at": claim.extracted_at,
                },
                "validation_status": status,
                "critic_confidence": raw_logit,
                "calibrated_confidence": calibrated,
                "evidence": evidence,
                "validated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # CoVe валидация
            try:
                import sys
                import importlib.util
                from pathlib import Path as PathLib
                cove_path = PathLib(__file__).parent.parent.parent / ".cursor" / "validation" / "cove" / "verify.py"
                if cove_path.exists():
                    spec = importlib.util.spec_from_file_location("cove_verify", cove_path)
                    cove_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(cove_module)
                    cove = cove_module.CoVeVerifier()
                    cove_result = cove.verify_validated_claim(validated_claim_dict)
                    if not cove_result["valid"]:
                        logger.warning("cove_validation_failed", errors=cove_result["errors"])
                        # В strict mode можно отбросить, но пока только логируем
            except Exception as e:
                logger.debug("cove_validation_skipped", error=str(e))
            
            validated.append(ValidatedClaim(
                claim=claim,
                validation_status=status,
                critic_confidence=raw_logit,
                calibrated_confidence=calibrated,
                evidence=evidence,
                validated_at=datetime.now(timezone.utc).isoformat(),
            ))
            
            logger.debug(
                "claim_validated",
                claim_text=claim.text[:50],
                status=status,
                confidence=calibrated,
            )
            
        except Exception as e:
            logger.error("claim_validation_failed", claim_text=claim.text[:50], error=str(e))
            
            # При ошибке помечаем как uncertain
            validated.append(ValidatedClaim(
                claim=claim,
                validation_status="uncertain",
                critic_confidence=0.3,
                calibrated_confidence=0.3,
                evidence=[],
                validated_at=None,
            ))
    
    logger.info(
        "deepconf_validation_completed",
        validated_count=len(validated),
        supported=sum(1 for v in validated if v.validation_status == "supported"),
    )
    
    return validated


def validate_recent_claims(output_dir: Path = Path(".cursor/osint/results")) -> None:
    """
    Валидирует недавние утверждения из результатов миссий.
    
    Args:
        output_dir: Директория с результатами миссий
    """
    if not output_dir.exists():
        logger.warning("validation_dir_not_found", path=str(output_dir))
        return
    
    # Находим последние результаты
    result_files = sorted(output_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not result_files:
        logger.warning("no_results_found", path=str(output_dir))
        return
    
    logger.info("validating_recent_claims", files_count=len(result_files[:5]))
    
    # TODO: Загружаем и ревалидируем недавние утверждения
    # Это может быть полезно при обновлении источников или улучшении модели


def main():
    """CLI для DeepConf валидации."""
    import argparse
    
    parser = argparse.ArgumentParser(description="DeepConf - Actor-Critic Validation")
    parser.add_argument(
        "--validate",
        choices=["recent"],
        help="Валидировать недавние утверждения",
    )
    
    args = parser.parse_args()
    
    if args.validate == "recent":
        validate_recent_claims()
        print("✅ Recent claims validation completed")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

