"""
Explainable AI — объяснение решений модели.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.utils.logging import get_logger

logger = get_logger("explainability")


class ExplainableAI:
    """Объяснение решений AI модели."""
    
    def explain_summary(
        self,
        summary: str,
        original_text: str,
        confidence_score: float,
        token_entropy: float,
        emotions: Optional[Dict[str, Any]] = None,
        key_facts: Optional[List[str]] = None,
        refined: bool = False,
    ) -> Dict[str, Any]:
        """
        Объясняет почему модель создала такое саммари.
        
        Args:
            summary: Сгенерированное саммари
            original_text: Исходный текст
            confidence_score: DeepConf confidence score
            token_entropy: Token entropy
            emotions: Результаты эмоционального анализа
            key_facts: Ключевые факты
            refined: Было ли саммари улучшено через Refiner
            
        Returns:
            Объяснение решения модели
        """
        explanation = {
            "summary": summary,
            "confidence_score": confidence_score,
            "token_entropy": token_entropy,
            "explanation": {
                "reasoning": self._generate_reasoning(confidence_score, token_entropy),
                "quality_assessment": self._assess_quality(confidence_score, token_entropy),
                "emotions_detected": emotions.get("emotions", []) if emotions else [],
                "key_facts": key_facts or [],
                "refined": refined,
                "factors": self._identify_factors(confidence_score, token_entropy, emotions),
            },
            "generated_at": datetime.now().isoformat(),
        }
        
        return explanation
    
    def _generate_reasoning(self, confidence: float, entropy: float) -> str:
        """Генерирует объяснение на основе метрик."""
        if confidence >= 0.9 and entropy <= 0.2:
            return "Очень высокая уверенность благодаря чётким фактам и низкой неопределённости модели"
        elif confidence >= 0.85 and entropy <= 0.3:
            return "Высокая уверенность с умеренной неопределённостью — саммари надёжное"
        elif confidence >= 0.7:
            return "Умеренная уверенность — саммари может содержать некоторые неточности"
        else:
            return "Низкая уверенность — рекомендуется ручная проверка"
    
    def _assess_quality(self, confidence: float, entropy: float) -> str:
        """Оценивает качество саммари."""
        if confidence >= 0.9 and entropy <= 0.2:
            return "excellent"
        elif confidence >= 0.85 and entropy <= 0.3:
            return "good"
        elif confidence >= 0.7:
            return "acceptable"
        else:
            return "needs_review"
    
    def _identify_factors(
        self,
        confidence: float,
        entropy: float,
        emotions: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Определяет факторы, влияющие на качество."""
        factors = []
        
        if confidence >= 0.85:
            factors.append("high_confidence")
        else:
            factors.append("low_confidence")
        
        if entropy <= 0.3:
            factors.append("low_uncertainty")
        else:
            factors.append("high_uncertainty")
        
        if emotions and emotions.get("emotions"):
            factors.append("emotions_detected")
        
        return factors
    
    def explain_emotion_analysis(self, emotion_result: Dict[str, Any]) -> Dict[str, Any]:
        """Объясняет результаты эмоционального анализа."""
        return {
            "emotions": emotion_result.get("emotions", []),
            "primary_emotion": emotion_result.get("primary_emotion"),
            "intensity": emotion_result.get("intensity", 0.0),
            "sentiment": emotion_result.get("sentiment", "neutral"),
            "method": emotion_result.get("method", "unknown"),
            "confidence": emotion_result.get("confidence", 0.5),
            "explanation": f"Обнаружена эмоция '{emotion_result.get('primary_emotion', 'нейтрально')}' с интенсивностью {emotion_result.get('intensity', 0.0):.2f}",
        }
    
    def explain_fact_extraction(self, facts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Объясняет извлечение фактов."""
        fact_types = {}
        for fact in facts:
            fact_type = fact.get("type", "fact")
            fact_types[fact_type] = fact_types.get(fact_type, 0) + 1
        
        return {
            "total_facts": len(facts),
            "fact_types": fact_types,
            "explanation": f"Извлечено {len(facts)} фактов: {', '.join(f'{k}: {v}' for k, v in fact_types.items())}",
        }


def get_explainer() -> ExplainableAI:
    """Фабричная функция для получения ExplainableAI."""
    return ExplainableAI()





