"""Менеджер промптов с единым интерфейсом."""
from typing import Any
from enum import Enum

from src.summarizer.prompts import (
    get_chain_of_density_prompt,
    get_few_shot_actions_prompt,
    get_critic_prompt,
)
# OSINT module archived (_archive/osint/) — scope creep, not used in production pipeline.


class PromptType(str, Enum):
    """Типы промптов."""
    CHAIN_OF_DENSITY = "chain_of_density"
    FEW_SHOT_ACTIONS = "few_shot_actions"
    CRITIC = "critic"
    EMOTION_ANALYSIS = "emotion_analysis"


class PromptManager:
    """Менеджер для получения промптов."""
    
    @staticmethod
    def get_prompt(
        prompt_type: PromptType | str,
        **kwargs: Any
    ) -> str:
        """
        Получает промпт по типу.
        
        Args:
            prompt_type: Тип промпта
            **kwargs: Параметры для промпта
            
        Returns:
            Текст промпта
            
        Raises:
            ValueError: Если тип промпта неизвестен
        """
        if isinstance(prompt_type, str):
            try:
                prompt_type = PromptType(prompt_type)
            except ValueError:
                raise ValueError(f"Unknown prompt type: {prompt_type}")
        
        if prompt_type == PromptType.CHAIN_OF_DENSITY:
            text = kwargs.get("text", "")
            iterations = kwargs.get("iterations", 5)
            return get_chain_of_density_prompt(text, iterations)
        
        elif prompt_type == PromptType.FEW_SHOT_ACTIONS:
            text = kwargs.get("text", "")
            examples = kwargs.get("examples")
            return get_few_shot_actions_prompt(text, examples)
        
        elif prompt_type == PromptType.CRITIC:
            summary = kwargs.get("summary", "")
            original_text = kwargs.get("original_text", "")
            return get_critic_prompt(summary, original_text)
        
        elif prompt_type == PromptType.EMOTION_ANALYSIS:
            text = kwargs.get("text", "")
            return f"""Проанализируй эмоциональное состояние в следующем тексте:

{text}

Определи:
1. Основные эмоции (радость, грусть, гнев, страх, удивление, отвращение и др.)
2. Интенсивность каждой эмоции (0.0-1.0)
3. Доминирующую эмоцию
4. Общую тональность (позитивная/нейтральная/негативная)

Формат ответа (JSON):
{{
    "emotions": ["эмоция1", "эмоция2"],
    "intensity": 0.0-1.0,
    "dominant_emotion": "эмоция",
    "sentiment": "positive|neutral|negative"
}}"""
        
        else:
            raise ValueError(f"Unknown prompt type: {prompt_type}")


def get_prompt(prompt_type: PromptType | str, **kwargs: Any) -> str:
    """
    Удобная функция для получения промпта.
    
    Args:
        prompt_type: Тип промпта
        **kwargs: Параметры для промпта
        
    Returns:
        Текст промпта
    """
    return PromptManager.get_prompt(prompt_type, **kwargs)
