"""
Reflexio Loop — основной цикл обработки с DeepConf-score.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.utils.logging import get_logger
from src.summarizer.chain_of_density import generate_dense_summary
from src.summarizer.critic import validate_summary
from src.summarizer.refiner import refine_summary
from src.summarizer.deepconf import calculate_confidence_score
from src.summarizer.emotion_analysis import analyze_emotions

logger = get_logger("loop.reflexio")


class ReflexioLoop:
    """Основной цикл обработки: Summarizer → Critic → Refiner."""
    
    def __init__(self):
        self.confidence_threshold = 0.85
        self.auto_refine = True
    
    def process(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Обрабатывает текст через полный pipeline.
        
        Args:
            text: Исходный текст
            metadata: Дополнительные метаданные
            
        Returns:
            {
                "summary": str,
                "confidence_score": float,
                "token_entropy": float,
                "refined": bool,
                "metrics": Dict,
            }
        """
        logger.info("reflexio_loop_started", text_length=len(text))
        
        # Шаг 0: Анализ эмоций (опционально)
        emotions_result = None
        try:
            emotions_result = analyze_emotions(text)
            logger.info("emotions_analyzed", emotions=emotions_result.get("emotions", []))
        except Exception as e:
            logger.warning("emotion_analysis_skipped", error=str(e))
        
        # Шаг 1: Summarizer (Chain of Density с эмоциональным контекстом)
        logger.info("step_1_summarizer")
        dense_summary_result = generate_dense_summary(text, iterations=3, include_emotions=True)
        summary = dense_summary_result["summary"]
        
        # Шаг 2: Critic (DeepConf validation)
        logger.info("step_2_critic")
        validated = validate_summary(
            summary,
            original_text=text,
            confidence_threshold=self.confidence_threshold,
            auto_refine=self.auto_refine,
        )
        
        # Шаг 3: Refiner (если нужно, уже вызван в validate_summary)
        # Но можем вызвать дополнительно если confidence всё ещё низкий
        if validated["confidence_score"] < self.confidence_threshold and self.auto_refine:
            logger.info("step_3_refiner_additional")
            refined_summary = refine_summary(validated["summary"], text)
            
            # Пересчитываем метрики
            refined_metrics = calculate_confidence_score(refined_summary, text, use_llm=True)
            
            if refined_metrics["confidence_score"] > validated["confidence_score"]:
                validated["summary"] = refined_summary
                validated["confidence_score"] = refined_metrics["confidence_score"]
                validated["token_entropy"] = refined_metrics["token_entropy"]
                validated["refined"] = True
        
        result = {
            "summary": validated["summary"],
            "confidence_score": validated["confidence_score"],
            "token_entropy": validated["token_entropy"],
            "refined": validated.get("refined", False),
            "metrics": validated["metrics"],
            "density_score": dense_summary_result.get("density_score", 0.0),
            "entities": dense_summary_result.get("entities", []),
            "key_facts": dense_summary_result.get("key_facts", []),
            "emotions": emotions_result if emotions_result else None,
            "processed_at": datetime.now().isoformat(),
        }
        
        logger.info(
            "reflexio_loop_completed",
            confidence=result["confidence_score"],
            refined=result["refined"],
        )
        
        # Обновляем core memory через self-update
        try:
            from src.memory.core_memory import get_core_memory
            core_memory = get_core_memory()
            core_memory.self_update_from_loop(result)
            logger.info("core_memory_updated_from_loop")
        except Exception as e:
            logger.warning("core_memory_update_skipped", error=str(e))
        
        return result
    
    def batch_process(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Обрабатывает несколько текстов.
        
        Args:
            texts: Список текстов
            
        Returns:
            Список результатов
        """
        results = []
        for text in texts:
            result = self.process(text)
            results.append(result)
        return results


def get_reflexio_loop() -> ReflexioLoop:
    """Фабричная функция для получения ReflexioLoop."""
    return ReflexioLoop()

