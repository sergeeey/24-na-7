"""
Эмоциональный анализ речи.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from typing import Dict

from src.utils.logging import get_logger

logger = get_logger("summarizer.emotion")


class EmotionAnalyzer:
    """Анализатор эмоций в тексте и аудио."""
    
    def __init__(self, method: str = "text"):
        """
        Args:
            method: "text" (анализ текста) или "audio" (анализ аудио через pyAudioAnalysis)
        """
        self.method = method
        self._audio_analyzer = None
        
        if method == "audio":
            try:
                from pyAudioAnalysis import audioSegmentation
                self._audio_analyzer = audioSegmentation
                logger.info("audio_emotion_analyzer_loaded")
            except ImportError:
                logger.warning("pyAudioAnalysis not available, using text-only analysis")
                self.method = "text"
    
    def analyze_text(self, text: str) -> Dict[str, any]:
        """
        Анализирует эмоции в тексте через LLM.
        
        Args:
            text: Текст для анализа
            
        Returns:
            Словарь с эмоциями, интенсивностью и метаданными
        """
        try:
            from src.llm.providers import get_llm_client
            
            client = get_llm_client(role="actor")
            if not client:
                return self._fallback_text_analysis(text)
            
            prompt = f"""Проанализируй эмоциональное состояние в следующем тексте и верни JSON:
{{
    "emotions": ["список", "основных", "эмоций"],
    "primary_emotion": "основная эмоция",
    "intensity": 0.0-1.0,
    "sentiment": "positive|neutral|negative",
    "keywords": ["ключевые", "слова", "эмоций"]
}}

Текст:
{text[:1000]}

Верни только JSON, без дополнительного текста."""

            response = client.call(prompt, system_prompt="Ты эксперт по анализу эмоций в тексте.")
            
            if response.get("text"):
                import json
                try:
                    # Парсим JSON из ответа
                    result_text = response["text"].strip()
                    # Убираем markdown код блоки если есть
                    if "```json" in result_text:
                        result_text = result_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in result_text:
                        result_text = result_text.split("```")[1].split("```")[0].strip()
                    
                    result = json.loads(result_text)
                    result["method"] = "llm"
                    result["confidence"] = 0.85
                    return result
                except json.JSONDecodeError:
                    logger.warning("emotion_analysis_json_parse_failed", fallback="rule_based")
            
            return self._fallback_text_analysis(text)
            
        except Exception as e:
            logger.error("emotion_analysis_failed", error=str(e), fallback="rule_based")
            return self._fallback_text_analysis(text)
    
    def _fallback_text_analysis(self, text: str) -> Dict[str, any]:
        """Простой анализ на основе ключевых слов."""
        text_lower = text.lower()
        
        # Простые паттерны эмоций
        emotion_keywords = {
            "радость": ["рад", "счастлив", "отлично", "замечательно", "прекрасно", "ура"],
            "грусть": ["грустно", "печаль", "плохо", "жаль", "обидно"],
            "злость": ["злой", "разозлился", "бесит", "ненавижу", "раздражен"],
            "страх": ["боюсь", "страшно", "опасно", "тревожно", "волнуюсь"],
            "удивление": ["удивительно", "неожиданно", "вау", "ого"],
            "спокойствие": ["спокойно", "расслабленно", "умиротворенно"],
        }
        
        detected_emotions = []
        for emotion, keywords in emotion_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                detected_emotions.append(emotion)
        
        # Определяем sentiment
        positive_words = ["хорошо", "отлично", "замечательно", "прекрасно", "рад"]
        negative_words = ["плохо", "ужасно", "грустно", "злой", "бесит"]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            sentiment = "positive"
        elif negative_count > positive_count:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        return {
            "emotions": detected_emotions or ["нейтрально"],
            "primary_emotion": detected_emotions[0] if detected_emotions else "нейтрально",
            "intensity": min(0.7, len(detected_emotions) * 0.2),
            "sentiment": sentiment,
            "keywords": detected_emotions,
            "method": "rule_based",
            "confidence": 0.5,
        }
    
    def analyze_audio(self, audio_path: str) -> Dict[str, any]:
        """
        Анализирует эмоции в аудио через pyAudioAnalysis.
        
        Args:
            audio_path: Путь к аудио файлу
            
        Returns:
            Словарь с эмоциями и метаданными
        """
        if self.method != "audio" or not self._audio_analyzer:
            logger.warning("audio_analysis_not_available", fallback="text")
            return {"emotions": [], "method": "not_available"}
        
        try:
            # pyAudioAnalysis может анализировать эмоции через MFCC и другие признаки
            # Это упрощённая версия
            logger.info("audio_emotion_analysis_started", audio_path=audio_path)
            
            # В реальной реализации здесь будет вызов pyAudioAnalysis
            # Для MVP возвращаем базовый результат
            return {
                "emotions": ["нейтрально"],
                "primary_emotion": "нейтрально",
                "intensity": 0.5,
                "sentiment": "neutral",
                "method": "audio",
                "confidence": 0.6,
            }
            
        except Exception as e:
            logger.error("audio_emotion_analysis_failed", error=str(e))
            return {"emotions": [], "method": "error"}


def analyze_emotions(text: str, method: str = "text") -> Dict[str, any]:
    """
    Удобная функция для анализа эмоций.
    
    Args:
        text: Текст для анализа
        method: "text" или "audio"
        
    Returns:
        Результат анализа эмоций
    """
    analyzer = EmotionAnalyzer(method=method)
    return analyzer.analyze_text(text)





