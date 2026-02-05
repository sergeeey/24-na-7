"""
Pipeline: Summarizer → Critic → Refiner
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import Dict, Any, Optional

from src.loop.reflexio_loop import ReflexioLoop

# Экспортируем основной pipeline
def process_text(text: str, **kwargs) -> Dict[str, Any]:
    """
    Удобная функция для обработки текста через pipeline.
    
    Args:
        text: Исходный текст
        **kwargs: Дополнительные параметры
        
    Returns:
        Результат обработки
    """
    loop = ReflexioLoop()
    return loop.process(text, metadata=kwargs)





